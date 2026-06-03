from sqlalchemy import (Column, String, Text, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.core.database import Base

class NotificationTemplate(Base):
    __tablename__ = "notification_templates"
    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id    = Column(UUID(as_uuid=True),
                          ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    trigger_type = Column(String(50), nullable=False)
    channel      = Column(String(20), nullable=False)
    language     = Column(String(10), nullable=False, default="en")
    subject      = Column(String(255))    # email subject only
    body         = Column(Text, nullable=False)
    # Variables: {{student_name}}, {{section}}, {{date}}, {{period}}, {{subject}},
    # {{teacher}}, {{attendance_pct}}, {{school_name}}, {{absent_count}},
    # {{leave_type}}, {{leave_dates}}
    is_active    = Column(Boolean, nullable=False, default=True)
    created_at   = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("branch_id", "trigger_type", "channel", "language",
                         name="uq_template"),
    )
