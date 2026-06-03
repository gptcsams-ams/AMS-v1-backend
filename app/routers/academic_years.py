from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_any, require_admin, require_super_admin
from app.models.academic_year import AcademicYear
from app.models.student_enrollment import StudentEnrollment
from app.schemas.academic_year import AcademicYearCreate, AcademicYearResponse, AcademicYearUpdate
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/academic-years")


@router.get("", response_model=list[AcademicYearResponse])
async def list_years(_: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(AcademicYear).order_by(AcademicYear.start_date.desc()))
    return list(rows.scalars().all())


@router.get("/current", response_model=AcademicYearResponse)
async def get_current_year(_: object = Depends(require_any), db: AsyncSession = Depends(get_db)):
    year = (await db.execute(select(AcademicYear).where(AcademicYear.is_current == True))).scalar_one_or_none()
    if not year:
        raise HTTPException(status_code=404, detail="Current academic year not configured")
    return year


@router.post("", response_model=AcademicYearResponse)
async def create_year(payload: AcademicYearCreate, _: object = Depends(require_super_admin), db: AsyncSession = Depends(get_db)):
    if payload.is_current:
        await db.execute(update(AcademicYear).where(AcademicYear.school_id == payload.school_id, AcademicYear.is_current == True).values(is_current=False))
    year = AcademicYear(**payload.model_dump())
    db.add(year)
    await db.commit()
    await db.refresh(year)
    return year


@router.patch("/{year_id}", response_model=AcademicYearResponse)
async def update_year(year_id: UUID, payload: AcademicYearUpdate, _: object = Depends(require_super_admin), db: AsyncSession = Depends(get_db)):
    year = (await db.execute(select(AcademicYear).where(AcademicYear.id == year_id))).scalar_one_or_none()
    if not year:
        raise HTTPException(status_code=404, detail="Academic year not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_current") is True:
        await db.execute(update(AcademicYear).where(AcademicYear.school_id == year.school_id, AcademicYear.is_current == True).values(is_current=False))
    for key, value in changes.items():
        setattr(year, key, value)
    await db.commit()
    await db.refresh(year)
    return year


@router.post("/{year_id}/set-current", response_model=AcademicYearResponse)
async def set_current_year(year_id: UUID, _: object = Depends(require_super_admin), db: AsyncSession = Depends(get_db)):
    year = (await db.execute(select(AcademicYear).where(AcademicYear.id == year_id))).scalar_one_or_none()
    if not year:
        raise HTTPException(status_code=404, detail="Academic year not found")
    await db.execute(update(AcademicYear).where(AcademicYear.school_id == year.school_id, AcademicYear.is_current == True).values(is_current=False))
    year.is_current = True
    await db.commit()
    await db.refresh(year)
    return year


@router.post("/{year_id}/rollover", response_model=MessageResponse)
async def rollover_year(year_id: UUID, _: object = Depends(require_super_admin), db: AsyncSession = Depends(get_db)):
    current = (await db.execute(select(AcademicYear).where(AcademicYear.id == year_id))).scalar_one_or_none()
    if not current:
        raise HTTPException(status_code=404, detail="Academic year not found")

    next_year = (await db.execute(
        select(AcademicYear).where(AcademicYear.school_id == current.school_id, AcademicYear.start_date > current.start_date).order_by(AcademicYear.start_date.asc())
    )).scalar_one_or_none()
    if not next_year:
        raise HTTPException(status_code=400, detail="Next academic year not configured")

    enrollments = (await db.execute(
        select(StudentEnrollment).where(StudentEnrollment.academic_year_id == current.id, StudentEnrollment.status == "ACTIVE")
    )).scalars().all()

    created = 0
    for en in enrollments:
        exists = (await db.execute(
            select(StudentEnrollment).where(StudentEnrollment.student_id == en.student_id, StudentEnrollment.academic_year_id == next_year.id)
        )).scalar_one_or_none()
        if exists:
            continue
        db.add(
            StudentEnrollment(
                student_id=en.student_id,
                section_id=en.section_id,
                academic_year_id=next_year.id,
                roll_number=en.roll_number,
                status="ACTIVE",
                enrolled_at=next_year.start_date,
            )
        )
        created += 1

    await db.commit()
    return MessageResponse(message=f"Rollover completed: {created} enrollments created")
