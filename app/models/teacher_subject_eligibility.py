from sqlalchemy import Column, TIMESTAMP, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class TeacherSubjectEligibility(Base):
    __tablename__ = "teacher_subject_eligibilities"
    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_profile_id = Column(UUID(as_uuid=True),
                                ForeignKey("teacher_profiles.id", ondelete="CASCADE"),
                                nullable=False)
    subject_id         = Column(UUID(as_uuid=True),
                                ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    class_id           = Column(UUID(as_uuid=True),
                                ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    created_at         = Column(TIMESTAMP, server_default=func.now())

    teacher = relationship("TeacherProfile", back_populates="subject_eligibilities")
    subject = relationship("Subject", back_populates="eligibilities")

    __table_args__ = (
        UniqueConstraint("teacher_profile_id", "subject_id", "class_id",
                         name="uq_teacher_subject_class"),
        Index("idx_elig_teacher", "teacher_profile_id"),
        Index("idx_elig_subject", "subject_id"),
        Index("idx_elig_class", "class_id"),
    )
