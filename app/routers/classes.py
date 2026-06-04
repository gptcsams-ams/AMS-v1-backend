from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin, require_any, require_super_admin
from app.models.academic_class import AcademicClass
from app.models.attendance import Attendance
from app.models.section import Section
from app.schemas.classes import ClassCreate, ClassResponse, ClassUpdate
from app.schemas.common import MessageResponse
from app.schemas.section import SectionResponse

router = APIRouter(prefix="/classes")


@router.get("", response_model=list[ClassResponse])
async def list_classes(
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(select(AcademicClass).order_by(AcademicClass.created_at.desc()))
    return list(rows.scalars().all())


@router.get("/{class_id}", response_model=ClassResponse)
async def get_class(
    class_id: UUID,
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(AcademicClass).where(AcademicClass.id == class_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Class not found")
    return row


@router.get("/{class_id}/sections", response_model=list[SectionResponse])
async def get_class_sections(
    class_id: UUID,
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(select(Section).where(Section.class_id == class_id).order_by(Section.name.asc()))
    return list(rows.scalars().all())


@router.get("/{class_id}/attendance")
async def get_class_attendance(
    class_id: UUID,
    from_date: date = Query(...),
    to_date: date = Query(...),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    section_ids = (await db.execute(select(Section.id).where(Section.class_id == class_id))).scalars().all()
    if not section_ids:
        return []
    rows = await db.execute(
        select(Attendance).where(
            Attendance.section_id.in_(section_ids),
            Attendance.attendance_date >= from_date,
            Attendance.attendance_date <= to_date,
        )
    )
    return list(rows.scalars().all())


@router.post("", response_model=ClassResponse)
async def create_class(
    payload: ClassCreate,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(
        select(AcademicClass).where(
            AcademicClass.branch_id == payload.branch_id,
            AcademicClass.grade == payload.grade,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Grade '{payload.grade}' already exists for this branch")

    row = AcademicClass(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.patch("/{class_id}", response_model=ClassResponse)
async def update_class(
    class_id: UUID,
    payload: ClassUpdate,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(AcademicClass).where(AcademicClass.id == class_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Class not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{class_id}", response_model=MessageResponse)
async def delete_class(
    class_id: UUID,
    _: object = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(AcademicClass).where(AcademicClass.id == class_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Class not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Class deleted")
