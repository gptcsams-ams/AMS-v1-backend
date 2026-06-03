from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class ParentCreate(BaseModel):
    user_id: UUID
    full_name: str
    contact_number: str
    email: Optional[EmailStr] = None


class ParentUpdate(BaseModel):
    full_name: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    occupation: Optional[str] = None


class ParentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    full_name: str
    contact_number: str
    email: Optional[str] = None
    address: Optional[str] = None
    occupation: Optional[str] = None
    created_at: datetime


class ParentStudentLinkCreate(BaseModel):
    student_id: UUID
    relationship_type: str
    is_primary: bool = False
