from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BranchCreate(BaseModel):
    school_id: UUID
    name: str
    location: Optional[str] = None


class BranchUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None


class BranchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    name: str
    location: Optional[str] = None
    created_at: datetime
