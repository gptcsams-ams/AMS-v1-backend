from sqlalchemy import Column, String, Text, TIMESTAMP, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class Branch(Base):
    __tablename__ = "branches"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id  = Column(UUID(as_uuid=True),
                        ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    name       = Column(String(255), nullable=False)
    location   = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())

    school  = relationship("School", back_populates="branches")
    classes = relationship("AcademicClass", back_populates="branch",
                           cascade="all, delete-orphan")
    users   = relationship("User", back_populates="branch")
    __table_args__ = (Index("idx_branch_school_id", "school_id"),)
