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


@router.get("/attendance/weekly")
async def weekly_attendance_trend(
    branch_id: str | None = Query(default=None),
    year_id:   str | None = Query(default=None),
    current_user: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Returns attendance % for the last 7 school days — powers the TrendLine chart."""
    from datetime import timedelta

    effective_branch = branch_id or str(getattr(current_user, "branch_id", ""))
    if not year_id:
        row = (await db.execute(
            text("SELECT id::text FROM academic_years WHERE is_current=TRUE LIMIT 1")
        )).fetchone()
        year_id = row[0] if row else None

    today = date.today()
    days = []
    d = today
    while len(days) < 7:
        if d.weekday() < 6:   # Mon-Sat
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()

    rows = (await db.execute(text("""
        SELECT
            a.attendance_date,
            COUNT(*) FILTER (WHERE a.status IN ('PRESENT','LATE')) AS present,
            COUNT(*) AS total
        FROM attendance a
        JOIN sections s ON s.id = a.section_id
        JOIN classes  c ON c.id = s.class_id
        WHERE c.branch_id = :branch_id
          AND a.academic_year_id = :year_id
          AND a.attendance_date = ANY(:days)
        GROUP BY a.attendance_date
        ORDER BY a.attendance_date
    """), {
        "branch_id": effective_branch,
        "year_id": year_id,
        "days": days,
    })).mappings().fetchall()

    by_date = {str(r["attendance_date"]): r for r in rows}
    result = []
    for d in days:
        r = by_date.get(str(d))
        pct = round(r["present"] / r["total"] * 100, 1) if r and r["total"] else 0
        result.append({
            "date": str(d),
            "label": d.strftime("%a"),
            "pct": pct,
            "present": r["present"] if r else 0,
            "total": r["total"] if r else 0,
        })
    return result
