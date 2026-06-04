from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin, require_any
from app.models.attendance import Attendance
from app.models.period_slot import PeriodSlot
from app.models.section import Section
from app.models.student import Student
from app.models.student_enrollment import StudentEnrollment
from app.models.timetable_entry import TimetableEntry
from app.schemas.common import MessageResponse
from app.schemas.section import SectionCreate, SectionResponse, SectionUpdate

router = APIRouter()


@router.get("", response_model=list[SectionResponse])
async def list_sections(
    class_id: UUID | None = Query(default=None),
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Section)
    if class_id:
        stmt = stmt.where(Section.class_id == class_id)
    rows = await db.execute(stmt.order_by(Section.name.asc()))
    return list(rows.scalars().all())


@router.get("/{section_id}", response_model=SectionResponse)
async def get_section(
    section_id: UUID,
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(Section).where(Section.id == section_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Section not found")
    return row


@router.get("/{section_id}/students")
async def get_section_students(
    section_id: UUID,
    year_id: UUID | None = Query(default=None),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Student)
        .join(StudentEnrollment, StudentEnrollment.student_id == Student.id)
        .where(StudentEnrollment.section_id == section_id, Student.is_active == True)
    )
    if year_id:
        stmt = stmt.where(StudentEnrollment.academic_year_id == year_id)

    rows = await db.execute(
        stmt.order_by(Student.roll_number.asc(), Student.first_name.asc())
    )
    return list(rows.scalars().all())


@router.get("/{section_id}/attendance")
async def get_section_attendance(
    section_id: UUID,
    from_date: date = Query(...),
    to_date: date = Query(...),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(Attendance).where(
            Attendance.section_id == section_id,
            Attendance.attendance_date >= from_date,
            Attendance.attendance_date <= to_date,
        )
    )
    return list(rows.scalars().all())


@router.get("/{section_id}/timetable")
async def get_section_timetable(
    section_id: UUID,
    year_id: UUID = Query(...),
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(TimetableEntry)
        .join(PeriodSlot, PeriodSlot.id == TimetableEntry.period_slot_id)
        .where(PeriodSlot.section_id == section_id, TimetableEntry.academic_year_id == year_id)
    )
    return list(rows.scalars().all())


@router.post("", response_model=SectionResponse)
async def create_section(
    payload: SectionCreate,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(
        select(Section).where(
            Section.class_id == payload.class_id,
            Section.name == payload.name,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Section '{payload.name}' already exists for this grade")

    row = Section(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.patch("/{section_id}", response_model=SectionResponse)
async def update_section(
    section_id: UUID,
    payload: SectionUpdate,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(Section).where(Section.id == section_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Section not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{section_id}", response_model=MessageResponse)
async def delete_section(
    section_id: UUID,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(Section).where(Section.id == section_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Section not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Section deleted")
