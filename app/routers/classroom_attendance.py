from datetime import date as date_type
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin, require_any
from app.models.classroom_attendance_record import ClassroomAttendanceRecord
from app.models.student_enrollment import StudentEnrollment
from app.models.timetable_entry import TimetableEntry
from app.models.period_slot import PeriodSlot
from app.schemas.classroom_attendance import (
    ClassroomAttendanceBulkMarkRequest,
    ClassroomAttendanceMarkRequest,
    ClassroomAttendanceUpdateRequest,
)
from app.schemas.common import MessageResponse

router = APIRouter()


@router.get("")
async def list_records(
    timetable_entry_id: UUID = Query(...),
    date: date_type = Query(...),
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(ClassroomAttendanceRecord).where(
            ClassroomAttendanceRecord.timetable_entry_id == timetable_entry_id,
            ClassroomAttendanceRecord.date == date,
        )
    )
    return list(rows.scalars().all())


@router.get("/student/{student_id}")
async def student_records(
    student_id: UUID,
    timetable_entry_id: UUID | None = Query(default=None),
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ClassroomAttendanceRecord).where(
        ClassroomAttendanceRecord.student_id == student_id
    )
    if timetable_entry_id:
        stmt = stmt.where(ClassroomAttendanceRecord.timetable_entry_id == timetable_entry_id)
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.post("/mark")
async def mark_attendance(
    payload: ClassroomAttendanceMarkRequest,
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(
        select(ClassroomAttendanceRecord).where(
            ClassroomAttendanceRecord.timetable_entry_id == payload.timetable_entry_id,
            ClassroomAttendanceRecord.student_id == payload.student_id,
            ClassroomAttendanceRecord.date == payload.date,
        )
    )).scalar_one_or_none()

    if existing:
        existing.status = payload.status
        existing.marked_by_teacher_id = payload.marked_by_teacher_id
        await db.commit()
        return {"id": str(existing.id), "updated": True}

    row = ClassroomAttendanceRecord(
        timetable_entry_id=payload.timetable_entry_id,
        student_id=payload.student_id,
        date=payload.date,
        status=payload.status,
        marked_by_teacher_id=payload.marked_by_teacher_id,
    )
    db.add(row)
    await db.commit()
    return {"id": str(row.id), "updated": False}


@router.post("/mark-bulk")
async def mark_bulk(
    payload: ClassroomAttendanceBulkMarkRequest,
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    upserted = 0
    for item in payload.records:
        student_id = item.get("student_id")
        status = item.get("status")
        if not student_id or not status:
            continue

        existing = (await db.execute(
            select(ClassroomAttendanceRecord).where(
                ClassroomAttendanceRecord.timetable_entry_id == payload.timetable_entry_id,
                ClassroomAttendanceRecord.student_id == student_id,
                ClassroomAttendanceRecord.date == payload.date,
            )
        )).scalar_one_or_none()

        if existing:
            existing.status = status
            existing.marked_by_teacher_id = payload.marked_by_teacher_id
        else:
            db.add(ClassroomAttendanceRecord(
                timetable_entry_id=payload.timetable_entry_id,
                student_id=student_id,
                date=payload.date,
                status=status,
                marked_by_teacher_id=payload.marked_by_teacher_id,
            ))
        upserted += 1

    await db.commit()
    return {"upserted": upserted}


@router.post("/mark-section")
async def mark_section(
    timetable_entry_id: UUID = Query(...),
    date: date_type = Query(...),
    default_status: str = Query(default="ABSENT"),
    marked_by_teacher_id: UUID | None = Query(default=None),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Mark all enrolled students for a timetable entry on a date with a default status.
    Useful for bulk-absent then individually marking present."""
    entry = (await db.execute(
        select(TimetableEntry)
        .join(PeriodSlot, PeriodSlot.id == TimetableEntry.period_slot_id)
        .where(TimetableEntry.id == timetable_entry_id)
    )).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Timetable entry not found")

    slot = (await db.execute(
        select(PeriodSlot).where(PeriodSlot.id == entry.period_slot_id)
    )).scalar_one_or_none()

    enrollments = (await db.execute(
        select(StudentEnrollment).where(
            StudentEnrollment.section_id == slot.section_id,
            StudentEnrollment.academic_year_id == entry.academic_year_id,
        )
    )).scalars().all()

    upserted = 0
    for enrollment in enrollments:
        existing = (await db.execute(
            select(ClassroomAttendanceRecord).where(
                ClassroomAttendanceRecord.timetable_entry_id == timetable_entry_id,
                ClassroomAttendanceRecord.student_id == enrollment.student_id,
                ClassroomAttendanceRecord.date == date,
            )
        )).scalar_one_or_none()

        if not existing:
            db.add(ClassroomAttendanceRecord(
                timetable_entry_id=timetable_entry_id,
                student_id=enrollment.student_id,
                date=date,
                status=default_status,
                marked_by_teacher_id=marked_by_teacher_id,
            ))
            upserted += 1

    await db.commit()
    return {"seeded": upserted, "total_enrolled": len(enrollments)}


@router.patch("/{record_id}", response_model=MessageResponse)
async def update_record(
    record_id: UUID,
    payload: ClassroomAttendanceUpdateRequest,
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(
        select(ClassroomAttendanceRecord).where(ClassroomAttendanceRecord.id == record_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Record not found")
    row.status = payload.status
    if payload.marked_by_teacher_id is not None:
        row.marked_by_teacher_id = payload.marked_by_teacher_id
    await db.commit()
    return MessageResponse(message="Attendance record updated")


@router.delete("/{record_id}", response_model=MessageResponse)
async def delete_record(
    record_id: UUID,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(
        select(ClassroomAttendanceRecord).where(ClassroomAttendanceRecord.id == record_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Record not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Attendance record deleted")
