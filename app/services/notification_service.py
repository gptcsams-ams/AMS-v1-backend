"""NotificationService — core business logic for the AMS notification subsystem.

Design notes (Redis-free):
  - Throttle is implemented via a DB query on recent Notification rows.
  - Send-time window uses datetime.now(tz).time() compared to rule.send_time_from/to.
  - Dispatch is async and called directly (no Celery); callers wrap in
    BackgroundTasks for non-blocking behaviour.
  - WebSocket push uses the in-memory ConnectionManager.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.notification import (
    NotificationOutsideWindowError,
    NotificationRuleDisabledError,
    RecipientNotFoundError,
    TemplateNotFoundError,
)
from app.models.notification import (
    ChannelType,
    Notification,
    NotificationRule,
    NotificationTemplate,
    NotifStatus,
    TriggerType,
)
from app.models.parent import Parent
from app.models.student import Student
from app.providers.base import DispatchResult
from app.providers.msg91 import MSG91Provider
from app.providers.twilio_provider import TwilioProvider
from app.providers.sendgrid import SendGridProvider
from app.ws.connection_manager import notification_manager

log = logging.getLogger(__name__)

MAX_RETRIES = 5


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Public API ─────────────────────────────────────────────────────────────

    async def send(
        self,
        trigger_type: str,
        channel: str,
        branch_id: UUID,
        student_id: Optional[UUID] = None,
        parent_id: Optional[UUID] = None,
        variables: Optional[dict[str, str]] = None,
    ) -> Optional[UUID]:
        """Resolve template, check rules/throttle, persist PENDING row, dispatch."""
        variables = variables or {}

        # 1. Rule check
        rule = await self._get_rule(branch_id, trigger_type, channel)
        if rule:
            if not rule.is_enabled:
                raise NotificationRuleDisabledError(trigger_type, channel)
            if not self._in_send_window(rule):
                raise NotificationOutsideWindowError(trigger_type, channel)

        # 2. Throttle check (DB-based — no Redis)
        if rule and rule.throttle_minutes and student_id:
            throttled = await self._is_throttled(
                trigger_type, channel, student_id, rule.throttle_minutes
            )
            if throttled:
                log.debug("Throttled: %s/%s student=%s", trigger_type, channel, student_id)
                return None

        # 3. Resolve template
        lang = variables.get("language", "en")
        tpl  = await self._resolve_template(branch_id, trigger_type, channel, lang)
        if not tpl:
            raise TemplateNotFoundError(trigger_type, channel)

        # 3b. Inject Parent Portal deep-link variable ({{portal_link}}). Routes the
        #     parent straight to the relevant child's attendance view.
        if student_id and "portal_link" not in variables:
            variables = {
                **variables,
                "portal_link": self._build_portal_link(student_id),
                "student_id": str(student_id),
            }

        # 4. Render
        body    = self._render(tpl.body, variables)
        subject = self._render(tpl.subject, variables) if tpl.subject else None

        # 5. Resolve recipient contact
        to = await self._resolve_recipient(parent_id, student_id, channel)
        if not to:
            raise RecipientNotFoundError(channel)

        # 6. Persist PENDING row
        notif = Notification(
            branch_id    = branch_id,
            student_id   = student_id,
            parent_id    = parent_id,
            trigger_type = trigger_type,
            channel      = channel,
            status       = NotifStatus.PENDING,
            payload      = {"to": to, "subject": subject, "body": body, "variables": variables},
        )
        self.db.add(notif)
        await self.db.flush()  # get notif.id without full commit

        # 7. Dispatch immediately (BackgroundTask wraps this for non-blocking)
        await self._dispatch(notif)
        await self.db.commit()
        return notif.id

    async def bulk_send(
        self,
        trigger_type: str,
        channel: str,
        branch_id: UUID,
        student_ids: list[UUID],
        variables_per_student: Optional[dict[UUID, dict[str, str]]] = None,
    ) -> list[UUID]:
        """Queue one send per student; returns list of Notification IDs created."""
        ids: list[UUID] = []
        variables_per_student = variables_per_student or {}
        for sid in student_ids:
            try:
                nid = await self.send(
                    trigger_type=trigger_type,
                    channel=channel,
                    branch_id=branch_id,
                    student_id=sid,
                    variables=variables_per_student.get(sid, {}),
                )
                if nid:
                    ids.append(nid)
            except Exception as exc:
                log.warning("bulk_send skip student=%s: %s", sid, exc)
        return ids

    # ── List / detail ──────────────────────────────────────────────────────────

    async def list_notifications(
        self,
        branch_id: UUID,
        trigger_type: Optional[str] = None,
        channel: Optional[str] = None,
        status: Optional[str] = None,
        student_id: Optional[UUID] = None,
        parent_id: Optional[UUID] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        page: int = 1,
        limit: int = 50,
    ) -> dict:
        q = select(Notification).where(Notification.branch_id == branch_id)
        if trigger_type:
            q = q.where(Notification.trigger_type == trigger_type)
        if channel:
            q = q.where(Notification.channel == channel)
        if status:
            q = q.where(Notification.status == status)
        if student_id:
            q = q.where(Notification.student_id == student_id)
        if parent_id:
            q = q.where(Notification.parent_id == parent_id)
        if from_date:
            q = q.where(Notification.created_at >= datetime.combine(from_date, datetime.min.time()))
        if to_date:
            q = q.where(Notification.created_at <= datetime.combine(to_date, datetime.max.time()))

        total = (await self.db.execute(
            select(func.count()).select_from(q.subquery())
        )).scalar_one()

        rows = (await self.db.execute(
            q.order_by(Notification.created_at.desc())
             .offset((page - 1) * limit)
             .limit(limit)
        )).scalars().all()

        return {
            "data": rows,
            "meta": {"total": total, "page": page, "limit": limit,
                     "pages": max(1, -(-total // limit))},
        }

    async def get_detail(self, notification_id: UUID, branch_id: UUID) -> Notification:
        row = (await self.db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.branch_id == branch_id,
            )
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Notification not found")
        return row

    # ── Rules ──────────────────────────────────────────────────────────────────

    async def list_rules(self, branch_id: UUID) -> list[NotificationRule]:
        return list((await self.db.execute(
            select(NotificationRule).where(NotificationRule.branch_id == branch_id)
        )).scalars().all())

    async def update_rule(
        self, branch_id: UUID, trigger_type: str, req: dict
    ) -> NotificationRule:
        rule = (await self.db.execute(
            select(NotificationRule).where(
                NotificationRule.branch_id == branch_id,
                NotificationRule.trigger_type == trigger_type,
                NotificationRule.channel == req.get("channel", "SMS"),
            )
        )).scalar_one_or_none()

        if not rule:
            rule = NotificationRule(
                branch_id=branch_id,
                trigger_type=trigger_type,
                channel=req.get("channel", "SMS"),
            )
            self.db.add(rule)

        for field, val in req.items():
            if hasattr(rule, field):
                setattr(rule, field, val)

        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    # ── Templates ──────────────────────────────────────────────────────────────

    async def list_templates(self, branch_id: UUID) -> list[NotificationTemplate]:
        return list((await self.db.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.branch_id == branch_id,
                NotificationTemplate.is_active == True,
            )
        )).scalars().all())

    async def create_template(self, branch_id: UUID, data: dict) -> NotificationTemplate:
        from sqlalchemy.exc import IntegrityError
        tpl = NotificationTemplate(branch_id=branch_id, **data)
        self.db.add(tpl)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            err = str(exc.orig).lower()
            if "uq_template" in err or "unique" in err:
                raise HTTPException(status_code=409, detail={
                    "code": "DUPLICATE",
                    "message": "Template for this branch/trigger/channel/language already exists",
                })
            raise HTTPException(status_code=400, detail={
                "code": "VALIDATION_ERROR",
                "message": str(exc.orig),
            })
        await self.db.refresh(tpl)
        return tpl

    async def update_template(
        self, template_id: UUID, branch_id: UUID, data: dict
    ) -> NotificationTemplate:
        tpl = (await self.db.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.id == template_id,
                NotificationTemplate.branch_id == branch_id,
            )
        )).scalar_one_or_none()
        if not tpl:
            raise HTTPException(status_code=404, detail="Template not found")
        for field, val in data.items():
            if hasattr(tpl, field):
                setattr(tpl, field, val)
        await self.db.commit()
        await self.db.refresh(tpl)
        return tpl

    async def delete_template(self, template_id: UUID, branch_id: UUID) -> None:
        tpl = (await self.db.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.id == template_id,
                NotificationTemplate.branch_id == branch_id,
            )
        )).scalar_one_or_none()
        if not tpl:
            raise HTTPException(status_code=404, detail="Template not found")
        tpl.is_active = False
        await self.db.commit()

    # ── Webhook delivery updates ───────────────────────────────────────────────

    async def handle_delivery_webhook(
        self, provider: str, provider_message_id: str, new_status: str
    ) -> None:
        row = (await self.db.execute(
            select(Notification).where(
                Notification.provider_message_id == provider_message_id
            )
        )).scalar_one_or_none()
        if not row:
            log.warning("Webhook: no notification found for provider_message_id=%s", provider_message_id)
            return

        now = datetime.now(timezone.utc)
        row.status = new_status
        if new_status == NotifStatus.DELIVERED:
            row.delivered_at = now
        elif new_status == NotifStatus.READ:
            row.read_at = now
        elif new_status == NotifStatus.FAILED:
            row.failure_reason = f"{provider} delivery failed"

        await self.db.commit()

        # Push real-time update to connected user
        event = {
            "type":            f"NOTIFICATION_{new_status}",
            "notification_id": str(row.id),
            "status":          new_status,
            "channel":         row.channel,
            "trigger_type":    row.trigger_type,
            "student_id":      str(row.student_id) if row.student_id else None,
            "timestamp":       now.isoformat(),
        }
        if row.parent_id:
            await notification_manager.send_to_user(str(row.parent_id), event)

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _get_rule(
        self, branch_id: UUID, trigger_type: str, channel: str
    ) -> Optional[NotificationRule]:
        return (await self.db.execute(
            select(NotificationRule).where(
                NotificationRule.branch_id == branch_id,
                NotificationRule.trigger_type == trigger_type,
                NotificationRule.channel == channel,
            )
        )).scalar_one_or_none()

    @staticmethod
    def _in_send_window(rule: NotificationRule) -> bool:
        if not rule.send_time_from or not rule.send_time_to:
            return True
        now_time = datetime.now(timezone.utc).time().replace(tzinfo=None)
        return rule.send_time_from <= now_time <= rule.send_time_to

    async def _is_throttled(
        self, trigger_type: str, channel: str, student_id: UUID, throttle_minutes: int
    ) -> bool:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=throttle_minutes)
        count = (await self.db.execute(
            select(func.count()).where(
                Notification.trigger_type == trigger_type,
                Notification.channel == channel,
                Notification.student_id == student_id,
                Notification.status.in_([NotifStatus.SENT, NotifStatus.DELIVERED,
                                          NotifStatus.PENDING]),
                Notification.created_at >= cutoff,
            )
        )).scalar_one()
        return count > 0

    async def _resolve_template(
        self, branch_id: UUID, trigger_type: str, channel: str, language: str
    ) -> Optional[NotificationTemplate]:
        tpl = (await self.db.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.branch_id == branch_id,
                NotificationTemplate.trigger_type == trigger_type,
                NotificationTemplate.channel == channel,
                NotificationTemplate.language == language,
                NotificationTemplate.is_active == True,
            )
        )).scalar_one_or_none()
        if not tpl and language != "en":
            # Fallback to English
            tpl = (await self.db.execute(
                select(NotificationTemplate).where(
                    NotificationTemplate.branch_id == branch_id,
                    NotificationTemplate.trigger_type == trigger_type,
                    NotificationTemplate.channel == channel,
                    NotificationTemplate.language == "en",
                    NotificationTemplate.is_active == True,
                )
            )).scalar_one_or_none()
        return tpl

    @staticmethod
    def _build_portal_link(student_id: UUID) -> str:
        """Deep-link into the Parent Portal scoped to a specific child."""
        from app.core.config import settings
        base = settings.PARENT_PORTAL_BASE_URL.rstrip("/")
        return f"{base}/parent/attendance?child={student_id}"

    @staticmethod
    def _render(template: str, variables: dict[str, str]) -> str:
        def replace(match: re.Match) -> str:
            key = match.group(1).strip()
            return variables.get(key, match.group(0))
        return re.sub(r"\{\{(\w+)\}\}", replace, template)

    async def _resolve_recipient(
        self, parent_id: Optional[UUID], student_id: Optional[UUID], channel: str
    ) -> Optional[str]:
        if parent_id:
            parent = (await self.db.execute(
                select(Parent).where(Parent.id == parent_id)
            )).scalar_one_or_none()
            if parent:
                if channel in (ChannelType.SMS, ChannelType.WHATSAPP):
                    if parent.contact_number:
                        return parent.contact_number
                if channel == ChannelType.EMAIL:
                    if parent.email:
                        return parent.email

        if student_id:
            student = (await self.db.execute(
                select(Student).where(Student.id == student_id)
            )).scalar_one_or_none()
            if student:
                if channel in (ChannelType.SMS, ChannelType.WHATSAPP):
                    if student.contact_number:
                        return student.contact_number
                if channel == ChannelType.EMAIL:
                    if student.email:
                        return student.email

        return None

    async def _dispatch(self, notif: Notification) -> None:
        """Call provider and update Notification row status. Called inline."""
        payload = notif.payload
        to      = payload.get("to", "")
        body    = payload.get("body", "")
        subject = payload.get("subject") or "School Notification"

        result: DispatchResult
        try:
            if notif.channel == ChannelType.SMS:
                result = await MSG91Provider().send_sms(to, body)
            elif notif.channel == ChannelType.WHATSAPP:
                result = await TwilioProvider().send_whatsapp(to, body)
            elif notif.channel == ChannelType.EMAIL:
                result = await SendGridProvider().send_email(to, subject, body)
            else:
                log.warning("Unsupported channel %s for notification %s", notif.channel, notif.id)
                notif.status = NotifStatus.FAILED
                notif.failure_reason = f"Unsupported channel: {notif.channel}"
                return
        except Exception as exc:
            log.exception("Dispatch exception notification=%s", notif.id)
            notif.retry_count  += 1
            notif.failure_reason = str(exc)
            if notif.retry_count >= MAX_RETRIES:
                notif.status = NotifStatus.FAILED
            return

        now = datetime.now(timezone.utc)
        if result.success:
            notif.status              = NotifStatus.SENT
            notif.sent_at             = now
            notif.provider_message_id = result.provider_message_id
        else:
            notif.retry_count   += 1
            notif.failure_reason = result.error_message
            if notif.retry_count >= MAX_RETRIES:
                notif.status = NotifStatus.FAILED
                log.error("Notification %s permanently FAILED: %s", notif.id, result.error_message)
            else:
                log.warning("Notification %s dispatch failed (%d/%d): %s",
                            notif.id, notif.retry_count, MAX_RETRIES, result.error_message)
