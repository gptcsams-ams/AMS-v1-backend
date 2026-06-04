from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin, require_any
from app.models.branding import Branding
from app.models.school import School
from app.schemas.branding import BrandingResponse, BrandingUpdate

router = APIRouter()


@router.get("", response_model=BrandingResponse)
async def get_branding(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Branding).limit(1))
    branding = result.scalar_one_or_none()
    if not branding:
        school = (await db.execute(select(School).limit(1))).scalar_one_or_none()
        if not school:
            raise HTTPException(status_code=404, detail="School not configured")
        branding = Branding(school_id=school.id)
        db.add(branding)
        await db.commit()
        await db.refresh(branding)
    return branding


@router.patch("", response_model=BrandingResponse)
async def patch_branding(
    payload: BrandingUpdate,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    branding = (await db.execute(select(Branding).limit(1))).scalar_one_or_none()
    if not branding:
        school = (await db.execute(select(School).limit(1))).scalar_one_or_none()
        if not school:
            raise HTTPException(status_code=404, detail="School not configured")
        branding = Branding(school_id=school.id)
        db.add(branding)

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(branding, key, value)
    await db.commit()
    await db.refresh(branding)
    return branding


@router.post("/logo", response_model=BrandingResponse)
async def upload_logo(
    logo: UploadFile = File(...),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    branding = (await db.execute(select(Branding).limit(1))).scalar_one_or_none()
    if not branding:
        school = (await db.execute(select(School).limit(1))).scalar_one_or_none()
        if not school:
            raise HTTPException(status_code=404, detail="School not configured")
        branding = Branding(school_id=school.id)
        db.add(branding)

    branding.logo_url = f"/media/branding/{logo.filename}"
    await db.commit()
    await db.refresh(branding)
    return branding
