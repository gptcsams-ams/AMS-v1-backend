from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin, require_any
from app.models.period_slot import PeriodSlot
from app.models.teacher_subject_eligibility import TeacherSubjectEligibility
from app.models.timetable_entry import TimetableEntry
from app.models.timetable_frequency_target import TimetableFrequencyTarget
from app.schemas.common import MessageResponse
from app.schemas.timetable import (
    FrequencyTargetCreate,
    PeriodSlotCreate,
    PeriodSlotUpdate,
    TimetableEntryCreate,
    TimetableEntryUpdate,
)
from app.services.timetable_service import generate_draft, publish_timetable

router = APIRouter(prefix="/timetable")


@router.get("/sections/{section_id}")
async def get_section_timetable(section_id: UUID, _: object = Depends(require_any), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(TimetableEntry)
        .join(PeriodSlot, PeriodSlot.id == TimetableEntry.period_slot_id)
        .where(PeriodSlot.section_id == section_id)
    )
    return list(rows.scalars().all())


@router.get("/sections/{section_id}/eligible-teachers")
async def get_eligible_teachers(section_id: UUID, _: object = Depends(require_any), db: AsyncSession = Depends(get_db)):
    _ = section_id
    rows = await db.execute(select(TeacherSubjectEligibility))
    return list(rows.scalars().all())


@router.get("/frequency-targets/{section_id}")
async def get_frequency_targets(section_id: UUID, year_id: UUID = Query(...), _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(TimetableFrequencyTarget).where(TimetableFrequencyTarget.section_id == section_id, TimetableFrequencyTarget.academic_year_id == year_id))
    return list(rows.scalars().all())


@router.post("/frequency-targets")
async def create_frequency_target(payload: FrequencyTargetCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = TimetableFrequencyTarget(**payload.model_dump())
    db.add(row)
    await db.commit()
    return {"id": str(row.id)}


@router.post("/period-slots")
async def create_period_slot(payload: PeriodSlotCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = PeriodSlot(**payload.model_dump())
    db.add(row)
    await db.commit()
    return {"id": str(row.id)}


@router.patch("/period-slots/{slot_id}")
async def update_period_slot(slot_id: UUID, payload: PeriodSlotUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(PeriodSlot).where(PeriodSlot.id == slot_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Period slot not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    return {"message": "Period slot updated"}


@router.delete("/period-slots/{slot_id}", response_model=MessageResponse)
async def delete_period_slot(slot_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(PeriodSlot).where(PeriodSlot.id == slot_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Period slot not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Period slot deleted")


@router.post("/entries")
async def create_entry(payload: TimetableEntryCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = TimetableEntry(**payload.model_dump())
    db.add(row)
    await db.commit()
    return {"id": str(row.id)}


@router.patch("/entries/{entry_id}")
async def update_entry(entry_id: UUID, payload: TimetableEntryUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(TimetableEntry).where(TimetableEntry.id == entry_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Entry not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    return {"message": "Entry updated"}


@router.delete("/entries/{entry_id}", response_model=MessageResponse)
async def delete_entry(entry_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(TimetableEntry).where(TimetableEntry.id == entry_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Entry not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Entry deleted")


@router.post("/sections/{section_id}/generate-draft")
async def generate_draft_route(section_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await generate_draft(db, section_id)


@router.post("/sections/{section_id}/publish")
async def publish_route(section_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await publish_timetable(db, section_id)


@router.post("/sections/{section_id}/unpublish")
async def unpublish_route(section_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(TimetableEntry)
        .join(PeriodSlot, PeriodSlot.id == TimetableEntry.period_slot_id)
        .where(PeriodSlot.section_id == section_id)
    )).scalars().all()
    for row in rows:
        row.is_published = False
    await db.commit()
    return {"message": "Unpublished"}
