from sqlalchemy import Column, String, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class Branding(Base):
    __tablename__ = "brandings"
    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id           = Column(UUID(as_uuid=True),
                                 ForeignKey("schools.id", ondelete="CASCADE"),
                                 nullable=False, unique=True)
    primary_color       = Column(String(7), nullable=False, default="#2563EB")
    secondary_color     = Column(String(7), default="#1E293B")
    accent_color        = Column(String(7), default="#3B82F6")
    logo_url            = Column(String(500))
    favicon_url         = Column(String(500))
    school_name_display = Column(String(255))
    updated_at          = Column(TIMESTAMP, server_default=func.now())

    school = relationship("School", back_populates="branding")
