from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TeacherCreate(BaseModel):
    user_id: Optional[UUID] = None
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    branch_id: Optional[UUID] = None
    employee_id: str
    department: Optional[str] = None
    designation: Optional[str] = None
    contact_number: Optional[str] = None
    profile_image_url: Optional[str] = None
    subject_ids: list[UUID] = []


class TeacherUpdate(BaseModel):
    branch_id: Optional[UUID] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    contact_number: Optional[str] = None
    profile_image_url: Optional[str] = None


class TeacherEligibilityResponse(BaseModel):
    id: UUID
    subject_id: UUID
    class_id: Optional[UUID] = None
    subject_name: Optional[str] = None
    grade: Optional[str] = None


class TeacherResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    branch_id: Optional[UUID] = None
    employee_id: str
    department: Optional[str] = None
    designation: Optional[str] = None
    profile_image_url: Optional[str] = None
    contact_number: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    eligibilities: list[TeacherEligibilityResponse] = []
    created_at: datetime


class TeacherEligibilityCreate(BaseModel):
    subject_id: UUID
    class_id: Optional[UUID] = None
