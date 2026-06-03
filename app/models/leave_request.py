from sqlalchemy import Column, String, Date, Boolean, Integer, TIMESTAMP, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id         = Column(UUID(as_uuid=True),
                                ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    academic_year_id   = Column(UUID(as_uuid=True),
                                ForeignKey("academic_years.id", ondelete="CASCADE"),
                                nullable=False)
    requested_by       = Column(UUID(as_uuid=True),
                                ForeignKey("users.id", ondelete="SET NULL"))
    from_date          = Column(Date, nullable=False)
    to_date            = Column(Date, nullable=False)
    reason             = Column(String(1000), nullable=False)
    leave_type         = Column(String(50), nullable=False)
                         # MEDICAL|PERSONAL|FAMILY|OTHER
    document_url       = Column(String(500))
    status             = Column(String(20), nullable=False, default="PENDING")
                         # PENDING|APPROVED|REJECTED|CANCELLED
    reviewed_by        = Column(UUID(as_uuid=True),
                                ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at        = Column(TIMESTAMP)
    review_remarks     = Column(String(500))
    affects_attendance = Column(Boolean, nullable=False, default=False)
    version            = Column(Integer, nullable=False, default=1)  # optimistic lock
    created_at         = Column(TIMESTAMP, server_default=func.now())

    student = relationship("Student")

    __table_args__ = (
        Index("idx_leave_student_year", "student_id", "academic_year_id"),
        Index("idx_leave_status", "status"),
    )

