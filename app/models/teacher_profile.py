from sqlalchemy import Column, String, TIMESTAMP, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class TeacherProfile(Base):
    __tablename__ = "teacher_profiles"
    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id           = Column(UUID(as_uuid=True),
                               ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    branch_id         = Column(UUID(as_uuid=True),
                               ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    employee_id       = Column(String(100), nullable=False)
    department        = Column(String(100))
    designation       = Column(String(100))
    profile_image_url = Column(String(500))
    contact_number    = Column(String(20))
    created_at        = Column(TIMESTAMP, server_default=func.now())

    user                  = relationship("User", back_populates="teacher_profile")
    subject_eligibilities = relationship("TeacherSubjectEligibility",
                                         back_populates="teacher",
                                         cascade="all, delete-orphan")
    timetable_entries     = relationship("TimetableEntry", back_populates="teacher")
    ptm_records                 = relationship("PTMRecord", back_populates="teacher")

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_teacher_user_id"),
        UniqueConstraint("branch_id", "employee_id", name="uq_employee_id_per_branch"),
        Index("idx_teacher_user_id", "user_id"),
        Index("idx_teacher_branch_id", "branch_id"),
    )
