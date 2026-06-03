from sqlalchemy import (Column, String, Date, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint, Index)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.core.database import Base

class AcademicYear(Base):
    __tablename__ = "academic_years"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id  = Column(UUID(as_uuid=True),
                        ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    name       = Column(String(20), nullable=False)    # "2024-2025"
    start_date = Column(Date, nullable=False)
    end_date   = Column(Date, nullable=False)
    is_current = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("school_id", "name", name="uq_academic_year"),
        # Partial unique index enforced in migration 004:
        # CREATE UNIQUE INDEX uq_one_current_year
        # ON academic_years(school_id) WHERE is_current = TRUE;
        Index("idx_academic_year_school", "school_id"),
    )
