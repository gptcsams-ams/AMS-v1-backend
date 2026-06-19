from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ClassroomAttendanceMarkRequest(BaseModel):
    timetable_entry_id: UUID
    student_id: UUID
    date: date
    status: str                         # PRESENT | ABSENT | LATE | EXCUSED
    marked_by_teacher_id: Optional[UUID] = None


class ClassroomAttendanceBulkMarkRequest(BaseModel):
    timetable_entry_id: UUID
    date: date
    marked_by_teacher_id: Optional[UUID] = None
    records: list[dict]                 # [{"student_id": "...", "status": "PRESENT"}, ...]


class ClassroomAttendanceUpdateRequest(BaseModel):
    status: str
    marked_by_teacher_id: Optional[UUID] = None
