from sqlalchemy import Column, Date, ForeignKey, Index, String, Time, TIMESTAMP, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.core.database import Base


class PTMRecord(Base):
    __tablename__ = "ptm_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(
        UUID(as_uuid=True),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("parents.id", ondelete="SET NULL"),
        nullable=True,
    )
    teacher_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teacher_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    section_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sections.id", ondelete="SET NULL"),
        nullable=True,
    )
    meeting_date = Column(Date, nullable=False)
    meeting_time = Column(Time, nullable=True)
    discussion = Column(Text, nullable=False)
    action_taken = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="OPEN")
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    student = relationship("Student", back_populates="ptm_records")
    parent = relationship("Parent", back_populates="ptm_records")
    teacher = relationship("TeacherProfile", back_populates="ptm_records")
    section = relationship("Section")

    __table_args__ = (
        Index("idx_ptm_student_date", "student_id", "meeting_date"),
        Index("idx_ptm_section_date", "section_id", "meeting_date"),
        Index("idx_ptm_parent_id", "parent_id"),
        Index("idx_ptm_teacher_id", "teacher_id"),
    )
