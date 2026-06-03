from sqlalchemy import Column, String, TIMESTAMP, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class Subject(Base):
    __tablename__ = "subjects"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id  = Column(UUID(as_uuid=True),
                        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    name       = Column(String(100), nullable=False)
    code       = Column(String(50))
    color      = Column(String(7), default="#6366F1")   # hex â€” used in timetable cells
    created_at = Column(TIMESTAMP, server_default=func.now())

    eligibilities     = relationship("TeacherSubjectEligibility", back_populates="subject")
    timetable_entries = relationship("TimetableEntry", back_populates="subject")

    __table_args__ = (
        UniqueConstraint("branch_id", "name", name="uq_subject_per_branch"),
        Index("idx_subject_branch_id", "branch_id"),
    )
