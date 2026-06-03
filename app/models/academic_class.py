from sqlalchemy import Column, String, TIMESTAMP, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class AcademicClass(Base):
    __tablename__ = "classes"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id  = Column(UUID(as_uuid=True),
                        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    grade      = Column(String(50), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    branch   = relationship("Branch", back_populates="classes")
    sections = relationship("Section", back_populates="academic_class",
                            cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint("branch_id", "grade", name="uq_grade_per_branch"),
        Index("idx_class_branch_id", "branch_id"),
    )
