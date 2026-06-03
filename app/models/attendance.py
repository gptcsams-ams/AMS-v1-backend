from sqlalchemy import (Column, String, Integer, Date, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint, Index)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class Attendance(Base):
    __tablename__ = "attendance"
    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id           = Column(UUID(as_uuid=True),
                                  ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    section_id           = Column(UUID(as_uuid=True),
                                  ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    academic_year_id     = Column(UUID(as_uuid=True),
                                  ForeignKey("academic_years.id", ondelete="CASCADE"),
                                  nullable=False)
    attendance_window_id = Column(UUID(as_uuid=True),
                                  ForeignKey("attendance_windows.id", ondelete="CASCADE"),
                                  nullable=False)
    attendance_date      = Column(Date, nullable=False)
    status               = Column(String(20), nullable=False)
                           # PRESENT|ABSENT|LATE|EXCUSED
    detection_count      = Column(Integer, default=0)
    first_detected_at    = Column(TIMESTAMP)
    last_detected_at     = Column(TIMESTAMP)
    captured_at          = Column(TIMESTAMP)
    data_confidence      = Column(String(20), default="HIGH")
                           # HIGH|LOW|MANUAL â€” LOW when camera had issues
    marked_by            = Column(String(20), nullable=False, default="SYSTEM")
                           # SYSTEM|TEACHER|ADMIN
    is_overridden        = Column(Boolean, nullable=False, default=False)
    override_reason      = Column(String(500))
    remarks              = Column(String(500))
    created_at           = Column(TIMESTAMP, server_default=func.now())

    student           = relationship("Student", back_populates="attendance_records")
    section           = relationship("Section", back_populates="attendance_records")
    attendance_window = relationship("AttendanceWindow", back_populates="attendance_records")

    __table_args__ = (
        UniqueConstraint("student_id", "attendance_window_id", "attendance_date",
                         name="uq_student_window_date"),
        Index("idx_att_student_year", "student_id", "academic_year_id"),
        Index("idx_att_section_date", "section_id", "attendance_date"),
        Index("idx_att_window_date", "attendance_window_id", "attendance_date"),
    )
    # Table partitioned by academic_year_id â€” see migration 031
