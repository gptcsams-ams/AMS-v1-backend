"""Notification background tasks.

Since Celery/Redis are not available in this deployment, tasks are implemented
as plain async functions. They can be:
  - called from FastAPI BackgroundTasks (already done in routes)
  - scheduled via APScheduler if added later
  - invoked from the /admin/tasks/* maintenance endpoints
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.core.database import AsyncSessionLocal
from app.models.notification import ChannelType, Notification, NotifStatus, TriggerType
from app.models.student import Student
from app.models.student_enrollment import StudentEnrollment
from app.models.attendance import Attendance
from sqlalchemy import select, func

log = logging.getLogger(__name__)


async def send_notification_task(notification_id: str) -> dict:
    """
    Retry-dispatch for a single Notification row that is still PENDING/FAILED.
    Useful for manual re-triggers or a scheduled retry sweep.
    """
    from app.services.notification_service import NotificationService, MAX_RETRIES

    async with AsyncSessionLocal() as db:
        svc = NotificationService(db)
        row = (await db.execute(
            select(Notification).where(Notification.id == notification_id)
        )).scalar_one_or_none()

        if not row:
            return {"ok": False, "reason": "not_found"}

        if row.status in (NotifStatus.SENT, NotifStatus.DELIVERED, NotifStatus.READ):
            return {"ok": True, "reason": "already_dispatched"}

        if row.retry_count >= MAX_RETRIES:
            return {"ok": False, "reason": "max_retries_exceeded"}

        await svc._dispatch(row)
        await db.commit()
        return {"ok": True, "status": row.status}


async def check_defaulters_task(threshold: float = 75.0) -> dict:
    """
    Daily task — finds students whose running attendance % is below `threshold`
    and sends DEFAULTER SMS notifications to their parents.

    Trigger this at 18:00 via APScheduler or a cron job hitting the
    /api/v1/tasks/check-defaulters admin endpoint.
    """
    from app.services.notification_service import NotificationService
    from app.models.student_parent import StudentParent

    count = 0
    async with AsyncSessionLocal() as db:
        # Aggregate: present_count / total_windows per student per branch
        subq = (
            select(
                Attendance.student_id,
                Attendance.section_id,
                func.count().label("total"),
                func.sum(
                    (Attendance.status == "PRESENT").cast(type_=func.count().type)
                ).label("present"),
            )
            .group_by(Attendance.student_id, Attendance.section_id)
            .subquery()
        )

        results = (await db.execute(
            select(subq).where(
                (subq.c.present * 100.0 / subq.c.total) < threshold
            )
        )).all()

        svc = NotificationService(db)

        for row in results:
            student = (await db.execute(
                select(Student).where(Student.id == row.student_id, Student.is_active == True)
            )).scalar_one_or_none()
            if not student:
                continue

            pct = round(row.present * 100.0 / row.total, 1) if row.total else 0.0

            # Find primary parent
            sp = (await db.execute(
                select(StudentParent).where(StudentParent.student_id == student.id)
            )).scalars().first()

            variables = {
                "student_name":    f"{student.first_name} {student.last_name}",
                "attendance_pct":  str(pct),
                "school_name":     "School",
            }
            try:
                await svc.send(
                    trigger_type = TriggerType.DEFAULTER,
                    channel      = ChannelType.SMS,
                    branch_id    = student.branch_id,
                    student_id   = student.id,
                    parent_id    = sp.parent_id if sp else None,
                    variables    = variables,
                )
                count += 1
            except Exception as exc:
                log.warning("check_defaulters skip student=%s: %s", student.id, exc)

    log.info("check_defaulters done: notified %d students", count)
    return {"notified": count}


async def camera_health_check_task() -> dict:
    """
    Every-5-minute task — detects cameras with stale heartbeats and sends
    CAMERA_OFFLINE notifications to admins.
    """
    from app.services.notification_service import NotificationService
    from app.models.camera import Camera
    from datetime import timedelta
    from app.models.user import User

    count = 0
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)

    async with AsyncSessionLocal() as db:
        stale_cameras = (await db.execute(
            select(Camera).where(
                Camera.stream_status != "OFFLINE",
                Camera.last_heartbeat < cutoff,
            )
        )).scalars().all()

        svc = NotificationService(db)

        for cam in stale_cameras:
            # Mark as offline
            cam.stream_status = "OFFLINE"

            # Notify branch admins
            admins = (await db.execute(
                select(User).where(
                    User.branch_id == cam.section.branch_id if hasattr(cam, "section") else True,
                    User.role.in_(["ADMIN", "SUPER_ADMIN"]),
                    User.is_active == True,
                )
            )).scalars().all()

            variables = {
                "camera_name": cam.name,
                "section_id":  str(cam.section_id),
            }
            for admin in admins[:1]:  # one notification per camera to one admin
                try:
                    await svc.send(
                        trigger_type = TriggerType.CAMERA_OFFLINE,
                        channel      = ChannelType.EMAIL,
                        branch_id    = admin.branch_id,
                        variables    = variables,
                    )
                    count += 1
                except Exception as exc:
                    log.warning("camera_health_check notify failed: %s", exc)

        await db.commit()

    return {"cameras_offline": len(stale_cameras), "notified": count}


async def cleanup_old_notifications_task(days: int = 90) -> dict:
    """
    Weekly task — archives Notification rows older than `days` days.
    Currently just deletes them; extend to copy to an archive table if needed.
    """
    from datetime import timedelta
    from sqlalchemy import delete

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(Notification).where(Notification.created_at < cutoff)
        )
        await db.commit()
        deleted = result.rowcount
    log.info("cleanup_old_notifications: deleted %d rows older than %d days", deleted, days)
    return {"deleted": deleted}
