from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_any, require_super_admin
from app.models.school import School
from app.schemas.school import SchoolResponse, SchoolUpdate

router = APIRouter(prefix="/school")


@router.get("", response_model=SchoolResponse)
async def get_school(
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    school = (await db.execute(select(School).limit(1))).scalar_one_or_none()
    if not school:
        raise HTTPException(status_code=404, detail="School not configured")
    return school


@router.patch("", response_model=SchoolResponse)
async def update_school(
    payload: SchoolUpdate,
    _: object = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    school = (await db.execute(select(School).limit(1))).scalar_one_or_none()
    if not school:
        raise HTTPException(status_code=404, detail="School not configured")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(school, key, value)

    await db.commit()
    await db.refresh(school)
    return school
