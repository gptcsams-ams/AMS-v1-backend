from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ClassCreate(BaseModel):
    branch_id: UUID
    grade: str


class ClassUpdate(BaseModel):
    grade: Optional[str] = None


class SectionNestedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    class_id: UUID
    name: str
    student_count: Optional[int] = None


class ClassResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    branch_id: UUID
    grade: str
    created_at: datetime
    section_count: Optional[int] = None
    student_count: Optional[int] = None
    avg_attendance_pct: Optional[float] = None
    sections: Optional[list[SectionNestedResponse]] = None
