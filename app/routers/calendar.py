from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models.school_calendar import SchoolCalendar
from app.schemas.calendar import CalendarCreate, CalendarUpdate

router = APIRouter()


@router.get("")
async def list_calendar(_: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return list((await db.execute(select(SchoolCalendar))).scalars().all())


@router.post("")
async def create_calendar(payload: CalendarCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = SchoolCalendar(**payload.model_dump())
    db.add(row)
    await db.commit()
    return {"id": str(row.id)}


@router.patch("/{entry_id}")
async def update_calendar(entry_id: UUID, payload: CalendarUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(SchoolCalendar).where(SchoolCalendar.id == entry_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Calendar entry not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    return {"message": "Calendar updated"}


@router.delete("/{entry_id}")
async def delete_calendar(entry_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(SchoolCalendar).where(SchoolCalendar.id == entry_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Calendar entry not found")
    await db.delete(row)
    await db.commit()
    return {"message": "Calendar deleted"}
