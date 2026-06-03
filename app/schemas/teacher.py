from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TeacherCreate(BaseModel):
    user_id: UUID
    branch_id: Optional[UUID] = None
    employee_id: str
    department: Optional[str] = None
    designation: Optional[str] = None


class TeacherUpdate(BaseModel):
    branch_id: Optional[UUID] = None
    department: Optional[str] = None
    designation: Optional[str] = None


class TeacherResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    branch_id: Optional[UUID] = None
    employee_id: str
    department: Optional[str] = None
    designation: Optional[str] = None
    created_at: datetime


class TeacherEligibilityCreate(BaseModel):
    subject_id: UUID
    class_id: UUID
