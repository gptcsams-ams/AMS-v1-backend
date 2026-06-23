import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, TIMESTAMP, ForeignKey,
    UniqueConstraint, Index, Time,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.core.database import Base


# ── Enums (string constants kept simple to avoid Alembic enum headaches) ───────

class TriggerType:
    ABSENT         = "ABSENT"
    LATE           = "LATE"
    DEFAULTER      = "DEFAULTER"
    CAMERA_OFFLINE = "CAMERA_OFFLINE"
    LEAVE_STATUS   = "LEAVE_STATUS"
    BULK           = "BULK"
    ALL = [ABSENT, LATE, DEFAULTER, CAMERA_OFFLINE, LEAVE_STATUS, BULK]


class ChannelType:
    SMS      = "SMS"
    WHATSAPP = "WHATSAPP"
    EMAIL    = "EMAIL"
    PUSH     = "PUSH"
    ALL = [SMS, WHATSAPP, EMAIL, PUSH]


class NotifStatus:
    PENDING   = "PENDING"
    SENT      = "SENT"
    DELIVERED = "DELIVERED"
    READ      = "READ"
    FAILED    = "FAILED"
    ALL = [PENDING, SENT, DELIVERED, READ, FAILED]


# ── NotificationTemplate ───────────────────────────────────────────────────────

class NotificationTemplate(Base):
    __tablename__ = "notification_templates"
    __table_args__ = (
        UniqueConstraint("branch_id", "trigger_type", "channel", "language",
                         name="uq_template"),
    )

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id    = Column(UUID(as_uuid=True),
                          ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    trigger_type = Column(String(50), nullable=False)
    channel      = Column(String(20), nullable=False)
    language     = Column(String(10), nullable=False, default="en")
    subject      = Column(String(255), nullable=True)   # email only
    body         = Column(Text, nullable=False)
    is_active    = Column(Boolean, nullable=False, default=True)
    created_at   = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at   = Column(TIMESTAMP(timezone=True), server_default=func.now(),
                          onupdate=func.now())


# ── NotificationRule ───────────────────────────────────────────────────────────

class NotificationRule(Base):
    __tablename__ = "notification_rules"
    __table_args__ = (
        UniqueConstraint("branch_id", "trigger_type", "channel",
                         name="uq_notif_rule"),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id        = Column(UUID(as_uuid=True),
                              ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    trigger_type     = Column(String(50), nullable=False)
    channel          = Column(String(20), nullable=False)
    is_enabled       = Column(Boolean, nullable=False, default=True)
    throttle_minutes = Column(Integer, nullable=True)   # min gap between same trigger/student
    send_time_from   = Column(Time, nullable=True)      # only send between from–to
    send_time_to     = Column(Time, nullable=True)
    created_at       = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at       = Column(TIMESTAMP(timezone=True), server_default=func.now(),
                              onupdate=func.now())


# ── Notification (dispatch log) ────────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notif_branch",    "branch_id"),
        Index("idx_notif_student",   "student_id"),
        Index("idx_notif_status",    "status"),
        Index("idx_notif_created",   "created_at"),
        Index("idx_notif_provider",  "provider_message_id"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id           = Column(UUID(as_uuid=True),
                                 ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    student_id          = Column(UUID(as_uuid=True),
                                 ForeignKey("students.id", ondelete="SET NULL"), nullable=True)
    parent_id           = Column(UUID(as_uuid=True),
                                 ForeignKey("parents.id", ondelete="SET NULL"), nullable=True)
    trigger_type        = Column(String(50), nullable=False)
    channel             = Column(String(20), nullable=False)
    status              = Column(String(20), nullable=False, default=NotifStatus.PENDING)
    sent_at             = Column(TIMESTAMP(timezone=True), nullable=True)
    delivered_at        = Column(TIMESTAMP(timezone=True), nullable=True)
    read_at             = Column(TIMESTAMP(timezone=True), nullable=True)
    failure_reason      = Column(String(500), nullable=True)
    retry_count         = Column(Integer, nullable=False, default=0)
    provider_message_id = Column(String(255), nullable=True)
    payload             = Column(JSONB, nullable=False, default=dict)
    created_at          = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at          = Column(TIMESTAMP(timezone=True), server_default=func.now(),
                                 onupdate=func.now())

    student = relationship("Student", lazy="selectin", foreign_keys=[student_id])
    parent  = relationship("Parent",  lazy="selectin", foreign_keys=[parent_id])
