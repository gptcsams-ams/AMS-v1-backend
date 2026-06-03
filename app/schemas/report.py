from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ReportJobCreate(BaseModel):
    student_id: UUID
    academic_year_id: UUID


class ReportJobResponse(BaseModel):
    job_id: str
    status: str
    result_url: Optional[str] = None
    updated_at: datetime
