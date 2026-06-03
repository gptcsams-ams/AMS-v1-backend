from sqlalchemy import Column, String, Float, Boolean, Date, TIMESTAMP, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
import uuid
from app.core.database import Base

class StudentFace(Base):
    __tablename__ = "student_faces"
    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id       = Column(UUID(as_uuid=True),
                              ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    image_url        = Column(String(500), nullable=False)
    embedding        = Column(Vector(512), nullable=False)
    quality_score    = Column(Float)
    blur_score       = Column(Float)         # reject if > 0.3
    brightness_score = Column(Float)         # reject < 30 or > 240
    face_angle_yaw   = Column(Float)         # reject if abs > 30 degrees
    face_angle_pitch = Column(Float)         # reject if abs > 20 degrees
    face_angle_roll  = Column(Float)
    face_bbox        = Column(JSONB)         # {"x":10,"y":20,"w":100,"h":120}
    source           = Column(String(50))    # MANUAL_UPLOAD|WEBCAM_CAPTURE|AUTO_TRAINED
    captured_date    = Column(Date)
    is_active        = Column(Boolean, nullable=False, default=True)
    created_at       = Column(TIMESTAMP, server_default=func.now())

    student = relationship("Student", back_populates="faces")

    __table_args__ = (Index("idx_face_student_id", "student_id"),)
    # IVFFlat index created in migration 030:
    # SET maintenance_work_mem = '512MB';
    # CREATE INDEX idx_face_embedding_ivfflat ON student_faces
    # USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
