from sqlalchemy import (Column, String, Boolean, Integer, Float, Time, TIMESTAMP, ForeignKey, UniqueConstraint, Index)
from sqlalchemy.dialects.postgresql import UUID, ARRAY, INTEGER
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class AttendanceWindow(Base):
    __tablename__ = "attendance_windows"
    id                             = Column(UUID(as_uuid=True), primary_key=True,
                                            default=uuid.uuid4)
    section_id                     = Column(UUID(as_uuid=True),
                                            ForeignKey("sections.id", ondelete="CASCADE"),
                                            nullable=False)
    timetable_entry_id             = Column(UUID(as_uuid=True),
                                            ForeignKey("timetable_entries.id",
                                                       ondelete="SET NULL"),
                                            nullable=True)   # NULL = manual mode
    name                           = Column(String(100), nullable=False)
    start_time                     = Column(Time, nullable=False)
    end_time                       = Column(Time, nullable=False)
    days_of_week                   = Column(ARRAY(INTEGER), nullable=False)
    is_manual_trigger              = Column(Boolean, nullable=False, default=False)
    is_active                      = Column(Boolean, nullable=False, default=True)
    min_detections_required        = Column(Integer, nullable=False, default=3)
    min_presence_minutes           = Column(Integer, nullable=False, default=5)
    confidence_threshold           = Column(Float, nullable=False, default=0.65)
    detection_start_offset_minutes  = Column(Integer, nullable=False, default=3)
    opening_capture_duration_minutes = Column(Integer, nullable=False, default=10)
    closing_capture_duration_minutes = Column(Integer, nullable=False, default=5)
    late_threshold_minutes           = Column(Integer, nullable=False, default=10)
    created_at                     = Column(TIMESTAMP, server_default=func.now())

    section            = relationship("Section", back_populates="attendance_windows")
    attendance_records = relationship("Attendance", back_populates="attendance_window",
                                      cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("section_id", "name", name="uq_window_name_per_section"),
        Index("idx_window_section_id", "section_id"),
    )
