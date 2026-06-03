from sqlalchemy import Column, String, Text, TIMESTAMP, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class School(Base):
    __tablename__ = "schools"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name       = Column(String(255), nullable=False)
    address    = Column(Text)
    state      = Column(String(100))
    city       = Column(String(100))
    area       = Column(String(100))
    pincode    = Column(String(20))
    phone      = Column(String(20))
    email      = Column(String(255))
    board      = Column(String(50))    # CBSE | ICSE | STATE | IB
    logo_url   = Column(String(500))
    created_at = Column(TIMESTAMP, server_default=func.now())

    branches = relationship("Branch", back_populates="school", cascade="all, delete-orphan")
    branding = relationship("Branding", back_populates="school", uselist=False)
    __table_args__ = (UniqueConstraint("name", name="uq_school_name"),)
