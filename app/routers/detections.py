from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models.detection import Detection

router = APIRouter(prefix="/detections")


@router.get("")
async def list_detections(
    section_id: UUID | None = Query(default=None),
    student_id: UUID | None = Query(default=None),
    on_date: date | None = Query(default=None),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Detection)
    if section_id:
        stmt = stmt.where(Detection.section_id == section_id)
    if student_id:
        stmt = stmt.where(Detection.student_id == student_id)
    if on_date:
        stmt = stmt.where(Detection.detected_at >= on_date, Detection.detected_at < (on_date.fromordinal(on_date.toordinal() + 1)))
    return list((await db.execute(stmt)).scalars().all())


@router.get("/{detection_id}")
async def get_detection(detection_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Detection).where(Detection.id == detection_id))).scalar_one_or_none()
