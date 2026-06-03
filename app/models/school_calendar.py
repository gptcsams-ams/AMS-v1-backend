from sqlalchemy import Column, String, Date, TIMESTAMP, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.core.database import Base

class SchoolCalendar(Base):
    __tablename__ = "school_calendar"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id  = Column(UUID(as_uuid=True),
                        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    date       = Column(Date, nullable=False)
    day_type   = Column(String(20), nullable=False)   # WORKING|HOLIDAY|HALF_DAY|EXAM
    reason     = Column(String(255))
    created_at = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("branch_id", "date", name="uq_calendar_date"),
        Index("idx_calendar_branch_date", "branch_id", "date"),
    )
