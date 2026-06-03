from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class AttendanceListFilter(BaseModel):
    section_id: Optional[UUID] = None


class AttendanceManualMarkRequest(BaseModel):
    student_id: UUID
    section_id: UUID
    academic_year_id: UUID
    attendance_window_id: UUID
    attendance_date: datetime
    status: str
