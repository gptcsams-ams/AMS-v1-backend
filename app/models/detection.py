from sqlalchemy import Column, String, Float, Boolean, TIMESTAMP, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class Detection(Base):
    __tablename__ = "detections"
    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id            = Column(UUID(as_uuid=True),
                                  ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    section_id           = Column(UUID(as_uuid=True),
                                  ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    attendance_window_id = Column(UUID(as_uuid=True),
                                  ForeignKey("attendance_windows.id", ondelete="SET NULL"),
                                  nullable=True)
    student_id           = Column(UUID(as_uuid=True),
                                  ForeignKey("students.id", ondelete="SET NULL"), nullable=True)
    tracking_id          = Column(String(100))
    confidence           = Column(Float)
    embedding_distance   = Column(Float)
    match_status         = Column(String(50), nullable=False)
                           # MATCHED|UNKNOWN|LOW_CONFIDENCE
    frame_brightness     = Column(Float)
    frame_quality_score  = Column(Float)
    image_url            = Column(String(500))
    used_for_training    = Column(Boolean, default=False)
    training_added_at    = Column(TIMESTAMP)
    detected_at          = Column(TIMESTAMP, server_default=func.now())

    camera  = relationship("Camera", back_populates="detections")
    section = relationship("Section", back_populates="detections")
    student = relationship("Student", back_populates="detections")

    __table_args__ = (
        Index("idx_detection_camera", "camera_id"),
        Index("idx_detection_section", "section_id"),
        Index("idx_detection_student", "student_id"),
        Index("idx_detection_window_time", "attendance_window_id", "detected_at"),
        Index("idx_detection_section_time", "section_id", "detected_at"),
    )
    # Table partitioned by academic_year_id â€” see migration 031
