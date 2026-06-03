from sqlalchemy import (Column, String, Date, TIMESTAMP, ForeignKey, UniqueConstraint, Index)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class StudentEnrollment(Base):
    __tablename__ = "student_enrollments"
    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id       = Column(UUID(as_uuid=True),
                              ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    section_id       = Column(UUID(as_uuid=True),
                              ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    academic_year_id = Column(UUID(as_uuid=True),
                              ForeignKey("academic_years.id", ondelete="CASCADE"),
                              nullable=False)
    roll_number      = Column(String(50), nullable=False)
    status           = Column(String(20), nullable=False, default="ACTIVE")
                       # ACTIVE | PROMOTED | DETAINED | TRANSFERRED | WITHDRAWN
    enrolled_at      = Column(Date, nullable=False)
    exited_at        = Column(Date)
    created_at       = Column(TIMESTAMP, server_default=func.now())

    student = relationship("Student", back_populates="enrollments")
    section = relationship("Section", back_populates="enrollments")

    __table_args__ = (
        UniqueConstraint("student_id", "academic_year_id", name="uq_student_per_year"),
        UniqueConstraint("section_id", "roll_number", "academic_year_id",
                         name="uq_roll_in_section_year"),
        Index("idx_enroll_student", "student_id"),
        Index("idx_enroll_section", "section_id"),
        Index("idx_enroll_year", "academic_year_id"),
    )
