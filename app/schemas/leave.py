from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class LeaveCreate(BaseModel):
    student_id: UUID
    academic_year_id: UUID
    from_date: date
    to_date: date
    reason: str
    leave_type: str


class LeaveReview(BaseModel):
    version: int
    status: str
    review_remarks: Optional[str] = None
