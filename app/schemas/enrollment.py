from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EnrollmentCreate(BaseModel):
    student_id: UUID
    section_id: UUID
    academic_year_id: UUID
    roll_number: str
    enrolled_at: date


class EnrollmentUpdate(BaseModel):
    section_id: Optional[UUID] = None
    roll_number: Optional[str] = None
    status: Optional[str] = None
    exited_at: Optional[date] = None


class EnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    section_id: UUID
    academic_year_id: UUID
    roll_number: str
    status: str
    enrolled_at: date
    exited_at: Optional[date] = None
    created_at: datetime
