"""
EmailSettings model — one row per branch.
Stores SMTP config for sending attendance emails to parents.
smtp_password is always stored encrypted (see app/core/crypto.py).
"""

import uuid

from sqlalchemy import (
    Boolean, Column, ForeignKey, Integer, String, Text, TIMESTAMP, Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class EmailSettings(Base):
    __tablename__ = "email_settings"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id     = Column(UUID(as_uuid=True),
                           ForeignKey("branches.id", ondelete="CASCADE"),
                           nullable=False, unique=True)

    # What parents see as the sender
    sender_name   = Column(String(255), nullable=True)
    sender_email  = Column(String(255), nullable=True)

    # SMTP connection details
    smtp_host     = Column(String(255), default="smtp.gmail.com")
    smtp_port     = Column(Integer,     default=587)
    smtp_user     = Column(String(255), nullable=True)
    smtp_password = Column(Text,        nullable=True)   # ENCRYPTED (Fernet)

    use_tls       = Column(Boolean, default=True)
    is_active     = Column(Boolean, default=False)

    created_at    = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), server_default=func.now(),
                           onupdate=func.now())

    __table_args__ = (
        Index("idx_email_settings_branch", "branch_id", unique=True),
    )
