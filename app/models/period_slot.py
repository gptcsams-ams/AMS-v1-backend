from sqlalchemy import (Column, String, Integer, Time, TIMESTAMP, ForeignKey, UniqueConstraint, Index)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class PeriodSlot(Base):
    __tablename__ = "period_slots"
    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id       = Column(UUID(as_uuid=True),
                              ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    academic_year_id = Column(UUID(as_uuid=True),
                              ForeignKey("academic_years.id", ondelete="CASCADE"),
                              nullable=False)
    day_of_week      = Column(Integer, nullable=False)    # 0=Mon â€¦ 4=Fri
    period_number    = Column(Integer, nullable=False)    # 1, 2, 3â€¦
    start_time       = Column(Time, nullable=False)
    end_time         = Column(Time, nullable=False)
    slot_type        = Column(String(20), nullable=False, default="CLASS")
                       # CLASS|BREAK|LUNCH|ASSEMBLY|FREE
    created_at       = Column(TIMESTAMP, server_default=func.now())

    section         = relationship("Section", back_populates="period_slots")
    timetable_entry = relationship("TimetableEntry", back_populates="period_slot",
                                   uselist=False)

    __table_args__ = (
        UniqueConstraint("section_id", "academic_year_id", "day_of_week", "period_number",
                         name="uq_period_slot"),
        Index("idx_period_slot_section_year", "section_id", "academic_year_id"),
    )
