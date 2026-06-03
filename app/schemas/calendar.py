from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class CalendarBase(BaseModel):
    branch_id: UUID
    date: date
    day_type: str
    reason: Optional[str] = None


class CalendarCreate(CalendarBase):
    pass


class CalendarUpdate(BaseModel):
    day_type: Optional[str] = None
    reason: Optional[str] = None


class CalendarResponse(CalendarBase):
    id: UUID

    class Config:
        from_attributes = True
