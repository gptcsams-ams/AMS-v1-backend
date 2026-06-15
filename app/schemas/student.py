from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StudentCreate(BaseModel):
    branch_id: Optional[UUID] = None
    section_id: Optional[UUID] = None
    academic_year_id: Optional[UUID] = None
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
    enrolled_at: Optional[date] = None


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
    section_id: Optional[UUID] = None
    academic_year_id: Optional[UUID] = None


class SectionRef(BaseModel):
    id: UUID
    class_id: UUID
    name: str
    grade: str


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
    face_image_url: Optional[str] = None
    face_count: int = 0
    is_active: bool
    created_at: datetime
    section: Optional[SectionRef] = None


class StudentFaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    image_url: str
    quality_score: Optional[float] = None
    blur_score: Optional[float] = None
    brightness_score: Optional[float] = None
    face_bbox: Optional[dict] = None
    source: Optional[str] = None
    captured_date: Optional[date] = None
    is_active: bool
    created_at: datetime
