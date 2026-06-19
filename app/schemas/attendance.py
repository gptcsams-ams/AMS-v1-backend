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


class AttendanceBulkMarkRequest(BaseModel):
    student_ids: list[UUID]
    section_id: UUID
    academic_year_id: UUID
    attendance_window_id: Optional[UUID] = None
    attendance_date: datetime
    status: str = "PRESENT"


class ClassroomManualMarkRequest(BaseModel):
    student_id: UUID
    section_id: UUID
    academic_year_id: Optional[UUID] = None
    attendance_date: datetime
    status: str
