from sqlalchemy import Column, String, Float, Date, TIMESTAMP, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.core.database import Base

class TestMark(Base):
    __tablename__ = "test_marks"
    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id         = Column(UUID(as_uuid=True), ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    student_id         = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    teacher_profile_id = Column(UUID(as_uuid=True), ForeignKey("teacher_profiles.id", ondelete="CASCADE"), nullable=False)
    subject_id         = Column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    academic_year_id   = Column(UUID(as_uuid=True), ForeignKey("academic_years.id", ondelete="SET NULL"), nullable=True)
    test_name          = Column(String(200), nullable=False)
    marks_obtained     = Column(Float, nullable=False)
    total_marks        = Column(Float, nullable=False)
    test_date          = Column(Date, nullable=True)
    created_at         = Column(TIMESTAMP, server_default=func.now())
    __table_args__     = (
        UniqueConstraint("section_id", "student_id", "test_name", "subject_id", name="uq_test_marks"),
        Index("ix_test_marks_student_id", "student_id"),
    )
