from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StudentCreate(BaseModel):
    branch_id: UUID
    first_name: str
    last_name: str
    admission_number: str
    roll_number: str
    dob: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    group_name: Optional[str] = None
    join_date: Optional[date] = None


class StudentUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    dob: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    roll_number: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    group_name: Optional[str] = None
    join_date: Optional[date] = None
    is_active: Optional[bool] = None


class StudentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    branch_id: UUID
    first_name: str
    last_name: str
    admission_number: str
    roll_number: str
    dob: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    group_name: Optional[str] = None
    join_date: Optional[date] = None
    student_photo_url: Optional[str] = None
    is_active: bool
    created_at: datetime
