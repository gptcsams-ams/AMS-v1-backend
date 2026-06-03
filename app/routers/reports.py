import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.core.redis import get_redis
from app.models.academic_record import AcademicRecord
from app.schemas.report import ReportJobCreate
from app.services.report_service import queue_report_card

router = APIRouter(prefix="/reports")


@router.get("/student/{student_id}")
async def student_reports(
    student_id: UUID,
    year_id: UUID | None = Query(default=None),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AcademicRecord).where(AcademicRecord.student_id == student_id)
    if year_id:
        stmt = stmt.where(AcademicRecord.academic_year_id == year_id)
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.post("/report-card")
async def generate_report_card(payload: ReportJobCreate, _: object = Depends(require_admin)):
    return await queue_report_card(str(payload.student_id), str(payload.academic_year_id))


@router.get("/jobs/{job_id}")
async def report_job_status(job_id: str, _: object = Depends(require_admin)):
    redis = get_redis()
    raw = await redis.get(f"report_job:{job_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Report job not found")
    return json.loads(raw)
