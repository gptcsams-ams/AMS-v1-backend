from sqlalchemy import Column, String, Float, Integer, TIMESTAMP, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class CameraHealthLog(Base):
    __tablename__ = "camera_health_logs"
    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id      = Column(UUID(as_uuid=True),
                            ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    status         = Column(String(20), nullable=False)   # ONLINE|OFFLINE|DEGRADED
    fps_actual     = Column(Float)
    frames_dropped = Column(Integer, default=0)
    error_message  = Column(String(500))
    logged_at      = Column(TIMESTAMP, server_default=func.now())

    camera = relationship("Camera", back_populates="health_logs")
    __table_args__ = (Index("idx_cam_health_cam_time", "camera_id", "logged_at"),)
    # Purge rows older than 30 days via Celery maintenance task
