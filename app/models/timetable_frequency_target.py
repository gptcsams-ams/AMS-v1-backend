from sqlalchemy import Column, Integer, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.core.database import Base

class TimetableFrequencyTarget(Base):
    __tablename__ = "timetable_frequency_targets"
    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id       = Column(UUID(as_uuid=True),
                              ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    academic_year_id = Column(UUID(as_uuid=True),
                              ForeignKey("academic_years.id", ondelete="CASCADE"),
                              nullable=False)
    subject_id       = Column(UUID(as_uuid=True),
                              ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    target_per_week  = Column(Integer, nullable=False)
    created_at       = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("section_id", "academic_year_id", "subject_id",
                         name="uq_freq_target"),
    )
