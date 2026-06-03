from sqlalchemy import (Column, String, Date, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint, Index)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class Student(Base):
    __tablename__ = "students"
    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id         = Column(UUID(as_uuid=True),
                               ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    first_name        = Column(String(100), nullable=False)
    last_name         = Column(String(100), nullable=False)
    dob               = Column(Date)
    gender            = Column(String(20))
    blood_group       = Column(String(5))
    roll_number       = Column(String(50), nullable=False)
    admission_number  = Column(String(50), nullable=False)
    contact_number    = Column(String(20))
    email             = Column(String(255))
    address           = Column(String(500))
    group_name        = Column(String(100))
    join_date         = Column(Date)
    student_photo_url = Column(String(500))
    is_active         = Column(Boolean, nullable=False, default=True)
    created_at        = Column(TIMESTAMP, server_default=func.now())

    enrollments        = relationship("StudentEnrollment", back_populates="student",
                                      cascade="all, delete-orphan")
    faces              = relationship("StudentFace", back_populates="student",
                                      cascade="all, delete-orphan")
    attendance_records = relationship("Attendance", back_populates="student",
                                      cascade="all, delete-orphan")
    detections         = relationship("Detection", back_populates="student")
    student_parents    = relationship("StudentParent", back_populates="student",
                                      cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("admission_number", name="uq_student_admission"),
        Index("idx_student_branch_id", "branch_id"),
        Index("idx_student_admission", "admission_number"),
    )
