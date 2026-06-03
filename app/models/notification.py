from sqlalchemy import Column, String, Text, TIMESTAMP, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.core.database import Base

class Notification(Base):
    __tablename__ = "notifications"
    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_id    = Column(UUID(as_uuid=True),
                             ForeignKey("users.id", ondelete="SET NULL"))
    recipient_phone = Column(String(20))
    recipient_email = Column(String(255))
    channel         = Column(String(20), nullable=False)   # SMS|WHATSAPP|EMAIL|PUSH
    trigger_type    = Column(String(50), nullable=False)
                      # ABSENT|LATE|DEFAULTER|CAMERA_OFFLINE|LEAVE_STATUS|BULK
    reference_id    = Column(UUID(as_uuid=True))
    reference_type  = Column(String(50))    # STUDENT|LEAVE_REQUEST
    message         = Column(Text, nullable=False)
    status          = Column(String(20), nullable=False, default="PENDING")
                      # PENDING|SENT|DELIVERED|READ|FAILED
    sent_at         = Column(TIMESTAMP)
    delivered_at    = Column(TIMESTAMP)
    read_at         = Column(TIMESTAMP)
    failure_reason  = Column(String(500))
    created_at      = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        Index("idx_notif_recipient", "recipient_id"),
        Index("idx_notif_status", "status"),
        Index("idx_notif_created", "created_at"),
    )
    # Purge rows older than 90 days via Celery maintenance task
