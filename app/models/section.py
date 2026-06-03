from sqlalchemy import Column, String, TIMESTAMP, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class Section(Base):
    __tablename__ = "sections"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_id   = Column(UUID(as_uuid=True),
                        ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    name       = Column(String(10), nullable=False)    # "A", "B", "C"
    created_at = Column(TIMESTAMP, server_default=func.now())

    academic_class     = relationship("AcademicClass", back_populates="sections")
    enrollments        = relationship("StudentEnrollment", back_populates="section")
    attendance_windows = relationship("AttendanceWindow", back_populates="section",
                                      cascade="all, delete-orphan")
    attendance_records = relationship("Attendance", back_populates="section",
                                      cascade="all, delete-orphan")
    cameras            = relationship("Camera", back_populates="section",
                                      cascade="all, delete-orphan")
    detections         = relationship("Detection", back_populates="section",
                                      cascade="all, delete-orphan")
    period_slots       = relationship("PeriodSlot", back_populates="section",
                                      cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint("class_id", "name", name="uq_section_per_class"),
        Index("idx_section_class_id", "class_id"),
    )
