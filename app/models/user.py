from sqlalchemy import (Column, String, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint, CheckConstraint, Index)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name         = Column(String(255), nullable=False)
    email        = Column(String(255), nullable=False)
    password     = Column(String(500), nullable=False)
    role         = Column(String(50), nullable=False)
    branch_id    = Column(UUID(as_uuid=True),
                          ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    is_active    = Column(Boolean, nullable=False, default=True)
    last_login   = Column(TIMESTAMP, nullable=True)
    totp_secret  = Column(String(200), nullable=True)
    totp_enabled = Column(Boolean, nullable=False, default=False)
    created_at   = Column(TIMESTAMP, server_default=func.now())

    branch          = relationship("Branch", back_populates="users")
    teacher_profile = relationship("TeacherProfile", back_populates="user", uselist=False)
    parent_profile  = relationship("Parent", back_populates="user", uselist=False)

    __table_args__ = (
        UniqueConstraint("email", name="uq_user_email"),
        CheckConstraint(
            "role IN ('SUPER_ADMIN','ADMIN','TEACHER','STUDENT','PARENT','FEE_ADMIN')",
            name="check_user_role"),
        Index("idx_user_branch_id", "branch_id"),
        Index("idx_user_role", "role"),
    )
