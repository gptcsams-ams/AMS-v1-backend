from sqlalchemy import Column, String, Date, TIMESTAMP, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base


class ClassroomAttendanceRecord(Base):
    __tablename__ = "classroom_attendance_records"
    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timetable_entry_id   = Column(UUID(as_uuid=True),
                                  ForeignKey("timetable_entries.id", ondelete="CASCADE"),
                                  nullable=False)
    student_id           = Column(UUID(as_uuid=True),
                                  ForeignKey("students.id", ondelete="CASCADE"),
                                  nullable=False)
    date                 = Column(Date, nullable=False)
    status               = Column(String(20), nullable=False)
                           # PRESENT | ABSENT | LATE | EXCUSED
    marked_by_teacher_id = Column(UUID(as_uuid=True),
                                  ForeignKey("teacher_profiles.id", ondelete="SET NULL"),
                                  nullable=True)
    created_at           = Column(TIMESTAMP, server_default=func.now())
    updated_at           = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    timetable_entry   = relationship("TimetableEntry",
                                     back_populates="classroom_attendance_records")
    student           = relationship("Student",
                                     back_populates="classroom_attendance_records")
    marked_by_teacher = relationship("TeacherProfile",
                                     back_populates="marked_classroom_attendance")

    __table_args__ = (
        UniqueConstraint("timetable_entry_id", "student_id", "date",
                         name="uq_classroom_attendance"),
        Index("idx_car_entry_date", "timetable_entry_id", "date"),
        Index("idx_car_student", "student_id"),
        Index("idx_car_teacher", "marked_by_teacher_id"),
    )
