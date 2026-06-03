from datetime import datetime, time
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FrequencyTargetCreate(BaseModel):
    section_id: UUID
    academic_year_id: UUID
    subject_id: UUID
    target_per_week: int


class PeriodSlotCreate(BaseModel):
    section_id: UUID
    academic_year_id: UUID
    day_of_week: int
    period_number: int
    start_time: time
    end_time: time
    slot_type: str = "CLASS"


class PeriodSlotUpdate(BaseModel):
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    slot_type: Optional[str] = None


class TimetableEntryCreate(BaseModel):
    period_slot_id: UUID
    academic_year_id: UUID
    subject_id: Optional[UUID] = None
    teacher_profile_id: Optional[UUID] = None


class TimetableEntryUpdate(BaseModel):
    subject_id: Optional[UUID] = None
    teacher_profile_id: Optional[UUID] = None
    is_published: Optional[bool] = None


class AttendanceWindowCreate(BaseModel):
    section_id: UUID
    timetable_entry_id: Optional[UUID] = None
    name: str
    start_time: time
    end_time: time
    days_of_week: list[int]
    is_manual_trigger: bool = False


class AttendanceWindowUpdate(BaseModel):
    name: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    days_of_week: Optional[list[int]] = None
    is_active: Optional[bool] = None


class AttendanceOverride(BaseModel):
    status: str
    reason: Optional[str] = None


class ManualAttendanceMark(BaseModel):
    student_id: UUID
    section_id: UUID
    academic_year_id: UUID
    attendance_window_id: UUID
    attendance_date: datetime
    status: str
