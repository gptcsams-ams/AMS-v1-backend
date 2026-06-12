from sqlalchemy import Column, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class TimetableEntry(Base):
    __tablename__ = "timetable_entries"
    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_slot_id     = Column(UUID(as_uuid=True),
                                ForeignKey("period_slots.id", ondelete="CASCADE"),
                                nullable=False)
    academic_year_id   = Column(UUID(as_uuid=True),
                                ForeignKey("academic_years.id", ondelete="CASCADE"),
                                nullable=False)
    subject_id         = Column(UUID(as_uuid=True),
                                ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    teacher_profile_id = Column(UUID(as_uuid=True),
                                ForeignKey("teacher_profiles.id", ondelete="SET NULL"),
                                nullable=True)
    is_published       = Column(Boolean, nullable=False, default=False)
    published_at       = Column(TIMESTAMP)
    created_at         = Column(TIMESTAMP, server_default=func.now())

    period_slot                  = relationship("PeriodSlot", back_populates="timetable_entry")
    subject                      = relationship("Subject", back_populates="timetable_entries")
    teacher                      = relationship("TeacherProfile", back_populates="timetable_entries")
    classroom_attendance_records = relationship("ClassroomAttendanceRecord",
                                                back_populates="timetable_entry",
                                                cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("period_slot_id", "academic_year_id", name="uq_timetable_entry"),
        Index("idx_tt_entry_slot", "period_slot_id"),
        Index("idx_tt_entry_teacher", "teacher_profile_id"),
    )
