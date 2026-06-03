from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin, require_super_admin
from app.models.teacher_profile import TeacherProfile
from app.models.teacher_subject_eligibility import TeacherSubjectEligibility
from app.models.timetable_entry import TimetableEntry
from app.schemas.common import MessageResponse
from app.schemas.teacher import TeacherCreate, TeacherEligibilityCreate, TeacherResponse, TeacherUpdate

router = APIRouter(prefix="/teachers")


@router.get("", response_model=list[TeacherResponse])
async def list_teachers(_: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(TeacherProfile))
    return list(rows.scalars().all())


@router.get("/{teacher_id}", response_model=TeacherResponse)
async def get_teacher(teacher_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(TeacherProfile).where(TeacherProfile.id == teacher_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return row


@router.get("/{teacher_id}/timetable")
async def get_teacher_timetable(teacher_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(TimetableEntry).where(TimetableEntry.teacher_profile_id == teacher_id))
    return list(rows.scalars().all())


@router.get("/{teacher_id}/eligibilities")
async def get_teacher_eligibilities(teacher_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(TeacherSubjectEligibility).where(TeacherSubjectEligibility.teacher_profile_id == teacher_id))
    return list(rows.scalars().all())


@router.post("", response_model=TeacherResponse)
async def create_teacher(payload: TeacherCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = TeacherProfile(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.post("/{teacher_id}/eligibilities")
async def add_eligibility(teacher_id: UUID, payload: TeacherEligibilityCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = TeacherSubjectEligibility(teacher_profile_id=teacher_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    return {"id": str(row.id)}


@router.delete("/{teacher_id}/eligibilities/{elig_id}", response_model=MessageResponse)
async def delete_eligibility(teacher_id: UUID, elig_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(TeacherSubjectEligibility).where(TeacherSubjectEligibility.id == elig_id, TeacherSubjectEligibility.teacher_profile_id == teacher_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Eligibility not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Eligibility deleted")


@router.patch("/{teacher_id}", response_model=TeacherResponse)
async def update_teacher(teacher_id: UUID, payload: TeacherUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(TeacherProfile).where(TeacherProfile.id == teacher_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Teacher not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{teacher_id}", response_model=MessageResponse)
async def delete_teacher(teacher_id: UUID, _: object = Depends(require_super_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(TeacherProfile).where(TeacherProfile.id == teacher_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Teacher not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Teacher deleted")
