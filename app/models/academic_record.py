from sqlalchemy import (Column, Float, Integer, String, Text, TIMESTAMP, ForeignKey, UniqueConstraint)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
from app.core.database import Base

class AcademicRecord(Base):
    __tablename__ = "academic_records"
    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id           = Column(UUID(as_uuid=True),
                                  ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    academic_year_id     = Column(UUID(as_uuid=True),
                                  ForeignKey("academic_years.id", ondelete="CASCADE"),
                                  nullable=False)
    section_id           = Column(UUID(as_uuid=True),
                                  ForeignKey("sections.id", ondelete="SET NULL"))
    promotion_status     = Column(String(20), nullable=False)
                           # PROMOTED|DETAINED|TRANSFERRED|WITHDRAWN
    final_attendance_pct = Column(Float)
    total_present        = Column(Integer)
    total_working_days   = Column(Integer)
    subject_attendance   = Column(JSONB)
    # {"Maths": {"pct": 85.0, "present": 42, "total": 50}}
    marks_summary        = Column(JSONB)    # reserved for v2 marks module
    remarks              = Column(Text)
    generated_at         = Column(TIMESTAMP)
    generated_by         = Column(UUID(as_uuid=True),
                                  ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        UniqueConstraint("student_id", "academic_year_id", name="uq_academic_record"),
    )
