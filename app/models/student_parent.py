from sqlalchemy import Column, String, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class StudentParent(Base):
    __tablename__ = "student_parents"
    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id        = Column(UUID(as_uuid=True),
                               ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    parent_id         = Column(UUID(as_uuid=True),
                               ForeignKey("parents.id", ondelete="CASCADE"), nullable=False)
    relationship_type = Column(String(50), nullable=False)   # FATHER|MOTHER|GUARDIAN
    is_primary        = Column(Boolean, nullable=False, default=True)
    created_at        = Column(TIMESTAMP, server_default=func.now())

    student = relationship("Student", back_populates="student_parents")
    parent  = relationship("Parent", back_populates="student_parents")

    __table_args__ = (UniqueConstraint("student_id", "parent_id", name="uq_student_parent"),)
