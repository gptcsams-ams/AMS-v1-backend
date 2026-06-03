from sqlalchemy import (Column, String, Boolean, Integer, TIMESTAMP, ForeignKey, UniqueConstraint, Index)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class Camera(Base):
    __tablename__ = "cameras"
    id                         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id                 = Column(UUID(as_uuid=True),
                                        ForeignKey("sections.id", ondelete="CASCADE"),
                                        nullable=False)
    name                       = Column(String(100), nullable=False)
    room_number                = Column(String(100), nullable=False)
    floor                      = Column(String(50))
    building                   = Column(String(100))
    rtsp_url                   = Column(String(1000), nullable=False)
    location_description       = Column(String(500))
    is_active                  = Column(Boolean, nullable=False, default=True)
    is_primary                 = Column(Boolean, nullable=False, default=True)
    frame_sample_interval_secs = Column(Integer, nullable=False, default=30)
    stream_status              = Column(String(20), default="UNKNOWN")
                                 # ACTIVE | OFFLINE | DEGRADED | UNKNOWN
    last_heartbeat             = Column(TIMESTAMP)
    reconnect_attempts         = Column(Integer, default=0)
    created_at                 = Column(TIMESTAMP, server_default=func.now())

    section     = relationship("Section", back_populates="cameras")
    detections  = relationship("Detection", back_populates="camera",
                               cascade="all, delete-orphan")
    health_logs = relationship("CameraHealthLog", back_populates="camera",
                               cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("rtsp_url", name="uq_camera_rtsp"),
        Index("idx_camera_section_id", "section_id"),
    )
