"""Notification routes — /api/v1/notifications/*

IMPORTANT: All fixed-path sub-routes (/rules, /templates, /send-bulk)
must be declared BEFORE /{notification_id} so FastAPI doesn't
treat those path segments as UUID values.
"""
from __future__ import annotations

import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models.user import User
from app.schemas.notification import (
    BulkSendRequest,
    BulkSendResponse,
    NotificationDetailResponse,
    NotificationListResponse,
    NotificationResponse,
    RuleResponse,
    RuleUpdateRequest,
    TemplateCreateRequest,
    TemplateResponse,
    TemplateUpdateRequest,
)
from app.services.notification_service import NotificationService

router = APIRouter()


# ── Rules  (before /{id} wildcard) ────────────────────────────────────────────

@router.get("/rules", response_model=list[RuleResponse])
async def list_rules(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    svc = NotificationService(db)
    return await svc.list_rules(current_user.branch_id)


@router.patch("/rules/{trigger_type}", response_model=RuleResponse)
async def update_rule(
    trigger_type: str,
    req:          RuleUpdateRequest,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    svc = NotificationService(db)
    return await svc.update_rule(
        current_user.branch_id,
        trigger_type,
        req.model_dump(exclude_unset=True),
    )


# ── Templates  (before /{id} wildcard) ────────────────────────────────────────

@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    svc = NotificationService(db)
    return await svc.list_templates(current_user.branch_id)


@router.post("/templates", response_model=TemplateResponse, status_code=201)
async def create_template(
    req:          TemplateCreateRequest,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    svc = NotificationService(db)
    return await svc.create_template(
        current_user.branch_id,
        req.model_dump(),
    )


@router.patch("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id:  UUID,
    req:          TemplateUpdateRequest,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    svc = NotificationService(db)
    return await svc.update_template(
        template_id,
        current_user.branch_id,
        req.model_dump(exclude_unset=True),
    )


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id:  UUID,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    svc = NotificationService(db)
    await svc.delete_template(template_id, current_user.branch_id)


# ── Bulk send  (before /{id} wildcard) ────────────────────────────────────────

@router.post("/send-bulk", response_model=BulkSendResponse, status_code=202)
async def send_bulk(
    req:          BulkSendRequest,
    background:   BackgroundTasks,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_admin),
):
    svc = NotificationService(db)

    async def _do_bulk():
        await svc.bulk_send(
            trigger_type          = req.trigger_type,
            channel               = req.channel,
            branch_id             = current_user.branch_id,
            student_ids           = req.student_ids,
            variables_per_student = {sid: req.variables for sid in req.student_ids},
        )

    background.add_task(_do_bulk)
    return BulkSendResponse(queued=len(req.student_ids), ids=[], status="QUEUED")


# ── Notification log list & detail  (wildcard last) ───────────────────────────

@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    trigger_type: Optional[str]           = Query(None),
    channel:      Optional[str]           = Query(None),
    status:       Optional[str]           = Query(None),
    student_id:   Optional[UUID]          = Query(None),
    parent_id:    Optional[UUID]          = Query(None),
    from_date:    Optional[datetime.date] = Query(None, alias="from"),
    to_date:      Optional[datetime.date] = Query(None, alias="to"),
    page:         int                     = Query(1, ge=1),
    limit:        int                     = Query(50, ge=1, le=100),
    db:           AsyncSession            = Depends(get_db),
    current_user: User                    = Depends(require_admin),
):
    svc    = NotificationService(db)
    result = await svc.list_notifications(
        branch_id    = current_user.branch_id,
        trigger_type = trigger_type,
        channel      = channel,
        status       = status,
        student_id   = student_id,
        parent_id    = parent_id,
        from_date    = from_date,
        to_date      = to_date,
        page         = page,
        limit        = limit,
    )
    return NotificationListResponse(
        data=[NotificationResponse.model_validate(r) for r in result["data"]],
        meta=result["meta"],
    )


@router.get("/{notification_id}", response_model=NotificationDetailResponse)
async def get_notification(
    notification_id: UUID,
    db:              AsyncSession = Depends(get_db),
    current_user:    User         = Depends(require_admin),
):
    svc = NotificationService(db)
    row = await svc.get_detail(notification_id, current_user.branch_id)
    return NotificationDetailResponse.from_orm_with_timeline(row)
