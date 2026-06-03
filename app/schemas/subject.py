from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SubjectCreate(BaseModel):
    branch_id: UUID
    name: str
    code: Optional[str] = None
    color: Optional[str] = "#6366F1"


class SubjectUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    color: Optional[str] = None


class SubjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    branch_id: UUID
    name: str
    code: Optional[str] = None
    color: Optional[str] = None
    created_at: datetime
