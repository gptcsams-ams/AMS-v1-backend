from sqlalchemy import Column, String, Text, Integer, Date, TIMESTAMP, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.core.database import Base

class Assignment(Base):
    __tablename__ = "assignments"
    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id         = Column(UUID(as_uuid=True), ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    teacher_profile_id = Column(UUID(as_uuid=True), ForeignKey("teacher_profiles.id", ondelete="CASCADE"), nullable=False)
    subject_id         = Column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    title              = Column(String(300), nullable=False)
    description        = Column(Text, nullable=True)
    due_date           = Column(Date, nullable=False)
    total_marks        = Column(Integer, default=10)
    created_at         = Column(TIMESTAMP, server_default=func.now())
    __table_args__     = (Index("ix_assignments_section_id", "section_id"),)
