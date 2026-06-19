from sqlalchemy import Column, String, TIMESTAMP, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class Parent(Base):
    __tablename__ = "parents"
    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id          = Column(UUID(as_uuid=True),
                              ForeignKey("users.id", ondelete="CASCADE"),
                              nullable=False, unique=True)
    full_name        = Column(String(100), nullable=False)
    contact_number   = Column(String(20), nullable=False)
    email            = Column(String(255))
    address          = Column(String(500))
    occupation       = Column(String(100))
    parent_photo_url = Column(String(500))
    created_at       = Column(TIMESTAMP, server_default=func.now())

    user            = relationship("User", back_populates="parent_profile")
    student_parents = relationship("StudentParent", back_populates="parent",
                                   cascade="all, delete-orphan")
    ptm_records     = relationship("PTMRecord", back_populates="parent")

    __table_args__ = (
        UniqueConstraint("contact_number", name="uq_parent_contact"),
        Index("idx_parent_contact", "contact_number"),
    )
