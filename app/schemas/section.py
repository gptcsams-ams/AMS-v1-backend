from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SectionCreate(BaseModel):
    class_id: UUID
    name: str


class SectionUpdate(BaseModel):
    name: Optional[str] = None


class SectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    class_id: UUID
    name: str
    created_at: datetime
