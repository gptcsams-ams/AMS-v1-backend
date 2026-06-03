from sqlalchemy import Column, String, TIMESTAMP, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
from app.core.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True),
                         ForeignKey("users.id", ondelete="SET NULL"))
    action      = Column(String(100), nullable=False)
    entity_type = Column(String(50))    # ATTENDANCE|STUDENT|TIMETABLE|LEAVE|CAMERAâ€¦
    entity_id   = Column(UUID(as_uuid=True))
    old_value   = Column(JSONB)
    new_value   = Column(JSONB)
    ip_address  = Column(String(45))
    user_agent  = Column(String(500))
    created_at  = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        Index("idx_audit_user", "user_id"),
        Index("idx_audit_entity", "entity_type", "entity_id"),
        Index("idx_audit_created", "created_at"),
    )
    # Retention: keep minimum 2 years
