from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.core.redis import get_redis
from app.models.attendance import Attendance
from app.models.attendance_window import AttendanceWindow
from app.schemas.attendance import AttendanceManualMarkRequest
from app.schemas.common import MessageResponse
from app.schemas.timetable import AttendanceOverride, AttendanceWindowCreate, AttendanceWindowUpdate

router = APIRouter()


@router.get("/attendance-windows")
async def list_windows(section_id: UUID | None = Query(default=None), _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    stmt = select(AttendanceWindow)
    if section_id:
        stmt = stmt.where(AttendanceWindow.section_id == section_id)
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.post("/attendance-windows")
async def create_window(payload: AttendanceWindowCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = AttendanceWindow(**payload.model_dump())
    db.add(row)
    await db.commit()
    return {"id": str(row.id)}


@router.patch("/attendance-windows/{window_id}")
async def update_window(window_id: UUID, payload: AttendanceWindowUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(AttendanceWindow).where(AttendanceWindow.id == window_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Window not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    return {"message": "Window updated"}


@router.delete("/attendance-windows/{window_id}", response_model=MessageResponse)
async def delete_window(window_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(AttendanceWindow).where(AttendanceWindow.id == window_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Window not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Window deleted")


@router.get("/attendance")
async def list_attendance(section_id: UUID | None = Query(default=None), _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    stmt = select(Attendance)
    if section_id:
        stmt = stmt.where(Attendance.section_id == section_id)
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.get("/attendance/live/{window_id}")
async def get_live_attendance(window_id: UUID, _: object = Depends(require_admin)):
    redis = get_redis()
    key = f"attendance:live:{window_id}:{date.today().isoformat()}"
    return await redis.hgetall(key)


@router.patch("/attendance/{attendance_id}/override")
async def override_attendance(attendance_id: UUID, payload: AttendanceOverride, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Attendance).where(Attendance.id == attendance_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    row.status = payload.status
    row.is_overridden = True
    row.override_reason = payload.reason
    row.marked_by = "ADMIN"
    await db.commit()
    return {"message": "Attendance overridden"}


@router.post("/attendance/mark-manual")
async def mark_manual(payload: AttendanceManualMarkRequest, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = Attendance(
        student_id=payload.student_id,
        section_id=payload.section_id,
        academic_year_id=payload.academic_year_id,
        attendance_window_id=payload.attendance_window_id,
        attendance_date=payload.attendance_date.date(),
        status=payload.status,
        marked_by="TEACHER",
        is_overridden=True,
    )
    db.add(row)
    await db.commit()
    return {"id": str(row.id)}


@router.get("/attendance/report/student/{student_id}")
async def student_report(student_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Attendance).where(Attendance.student_id == student_id))
    return list(rows.scalars().all())


@router.get("/attendance/report/section/{section_id}")
async def section_report(section_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Attendance).where(Attendance.section_id == section_id))
    return list(rows.scalars().all())


@router.get("/attendance/report/defaulters")
async def defaulters_report(_: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Attendance).where(Attendance.status == "ABSENT"))
    return list(rows.scalars().all())
