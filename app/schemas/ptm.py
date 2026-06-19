from datetime import date, datetime, time
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PTMRecordCreate(BaseModel):
    student_id: UUID
    parent_id: Optional[UUID] = None
    teacher_id: Optional[UUID] = None
    section_id: Optional[UUID] = None
    meeting_date: date
    meeting_time: Optional[time] = None
    discussion: str
    action_taken: str
    status: str = "OPEN"


class PTMRecordUpdate(BaseModel):
    parent_id: Optional[UUID] = None
    teacher_id: Optional[UUID] = None
    section_id: Optional[UUID] = None
    meeting_date: Optional[date] = None
    meeting_time: Optional[time] = None
    discussion: Optional[str] = None
    action_taken: Optional[str] = None
    status: Optional[str] = None


class PTMRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    parent_id: Optional[UUID] = None
    teacher_id: Optional[UUID] = None
    section_id: Optional[UUID] = None
    meeting_date: date
    meeting_time: Optional[time] = None
    discussion: str
    action_taken: str
    status: str
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    student_name: Optional[str] = None
    parent_name: Optional[str] = None
    teacher_name: Optional[str] = None
    class_name: Optional[str] = None


class PTMInitiateRequest(BaseModel):
    section_id: UUID
    meeting_date: date
    meeting_time: time
    message: str
