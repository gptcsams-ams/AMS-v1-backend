from datetime import date, datetime, time
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator


# ── Shared ─────────────────────────────────────────────────────────────────────

class PaginationMeta(BaseModel):
    total: int
    page:  int
    limit: int
    pages: int


# ── Template schemas ───────────────────────────────────────────────────────────

class TemplateCreateRequest(BaseModel):
    trigger_type: str
    channel:      str
    language:     str = "en"
    subject:      Optional[str] = None
    body:         str

    @field_validator("trigger_type")
    @classmethod
    def valid_trigger(cls, v: str) -> str:
        allowed = ["ABSENT", "LATE", "DEFAULTER", "CAMERA_OFFLINE", "LEAVE_STATUS", "BULK"]
        if v not in allowed:
            raise ValueError(f"trigger_type must be one of {allowed}")
        return v

    @field_validator("channel")
    @classmethod
    def valid_channel(cls, v: str) -> str:
        allowed = ["SMS", "WHATSAPP", "EMAIL", "PUSH"]
        if v not in allowed:
            raise ValueError(f"channel must be one of {allowed}")
        return v


class TemplateUpdateRequest(BaseModel):
    subject:   Optional[str] = None
    body:      Optional[str] = None
    language:  Optional[str] = None
    is_active: Optional[bool] = None


class TemplateResponse(BaseModel):
    id:           UUID
    branch_id:    UUID
    trigger_type: str
    channel:      str
    language:     str
    subject:      Optional[str]
    body:         str
    is_active:    bool
    created_at:   datetime
    updated_at:   Optional[datetime]

    model_config = {"from_attributes": True}


# ── Rule schemas ───────────────────────────────────────────────────────────────

class RuleUpdateRequest(BaseModel):
    channel:          str
    is_enabled:       Optional[bool] = None
    throttle_minutes: Optional[int]  = None
    send_time_from:   Optional[time] = None
    send_time_to:     Optional[time] = None


class RuleResponse(BaseModel):
    id:               UUID
    branch_id:        UUID
    trigger_type:     str
    channel:          str
    is_enabled:       bool
    throttle_minutes: Optional[int]
    send_time_from:   Optional[time]
    send_time_to:     Optional[time]
    created_at:       datetime
    updated_at:       Optional[datetime]

    model_config = {"from_attributes": True}


# ── Notification schemas ───────────────────────────────────────────────────────

class NotificationCreate(BaseModel):
    """Legacy schema for simple direct creates (kept for backward compat)."""
    recipient_id:    Optional[UUID] = None
    recipient_phone: Optional[str]  = None
    recipient_email: Optional[str]  = None
    channel:         str
    trigger_type:    str
    message:         str


class NotificationUpdate(BaseModel):
    message: Optional[str] = None
    status:  Optional[str] = None


class NotificationResponse(BaseModel):
    id:                  UUID
    branch_id:           Optional[UUID]
    student_id:          Optional[UUID]
    parent_id:           Optional[UUID]
    trigger_type:        str
    channel:             str
    status:              str
    sent_at:             Optional[datetime]
    delivered_at:        Optional[datetime]
    read_at:             Optional[datetime]
    failure_reason:      Optional[str]
    retry_count:         int
    provider_message_id: Optional[str]
    payload:             dict
    created_at:          datetime

    model_config = {"from_attributes": True}


class NotificationDetailResponse(NotificationResponse):
    timeline: list[dict] = []

    @classmethod
    def from_orm_with_timeline(cls, row: Any) -> "NotificationDetailResponse":
        obj = cls.model_validate(row)
        tl: list[dict] = []
        tl.append({"event": "CREATED",   "timestamp": row.created_at.isoformat() if row.created_at else None})
        if row.sent_at:
            tl.append({"event": "SENT",  "timestamp": row.sent_at.isoformat()})
        if row.delivered_at:
            tl.append({"event": "DELIVERED", "timestamp": row.delivered_at.isoformat()})
        if row.read_at:
            tl.append({"event": "READ",  "timestamp": row.read_at.isoformat()})
        obj.timeline = tl
        return obj


class NotificationListResponse(BaseModel):
    data: list[NotificationResponse]
    meta: PaginationMeta


# ── Bulk send schemas ──────────────────────────────────────────────────────────

class BulkSendRequest(BaseModel):
    trigger_type: str
    channel:      str
    student_ids:  list[UUID]
    variables:    dict[str, str] = {}


class BulkSendResponse(BaseModel):
    queued:  int
    ids:     list[UUID]
    status:  str = "QUEUED"
