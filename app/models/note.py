from sqlalchemy import Column, String, Text, TIMESTAMP, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class Note(Base):
    __tablename__ = "notes"
    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id         = Column(UUID(as_uuid=True), ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    teacher_profile_id = Column(UUID(as_uuid=True), ForeignKey("teacher_profiles.id", ondelete="CASCADE"), nullable=False)
    subject_id         = Column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    title              = Column(String(300), nullable=False)
    content            = Column(Text, nullable=False)
    created_at         = Column(TIMESTAMP, server_default=func.now())
    updated_at         = Column(TIMESTAMP, nullable=True)
    __table_args__     = (Index("ix_notes_section_id", "section_id"),)
