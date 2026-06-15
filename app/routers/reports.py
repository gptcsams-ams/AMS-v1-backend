from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models.academic_record import AcademicRecord
from app.schemas.report import ReportJobCreate
from app.services.report_service import queue_report_card

router = APIRouter()


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


@router.get("/attendance/daily")
async def daily_attendance_report(
    branch_id: str | None = Query(default=None),
    year_id:   str | None = Query(default=None),
    date_str:  str | None = Query(default=None, alias="date"),
    current_user: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.dashboard_service import get_dashboard_stats

    if not year_id:
        row = (await db.execute(
            text("SELECT id::text FROM academic_years WHERE is_current=TRUE LIMIT 1")
        )).fetchone()
        year_id = row[0] if row else None
    if not year_id:
        raise HTTPException(400, detail={"code": "NO_ACADEMIC_YEAR",
                                          "message": "No current academic year configured"})

    stats = await get_dashboard_stats(
        branch_id  = branch_id or str(getattr(current_user, "branch_id", "")),
        year_id    = year_id,
        today_date = date_str or str(date.today()),
        db         = db,
    )
    return {"data": stats}
