from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin, require_any
from app.models.academic_year import AcademicYear
from app.models.student_enrollment import StudentEnrollment
from app.schemas.academic_year import AcademicYearCreate, AcademicYearResponse, AcademicYearUpdate
from app.schemas.common import MessageResponse
from app.schemas.promotion import (
    PromotionExecuteRequest,
    PromotionExecuteResponse,
    PromotionJobStatus,
    PromotionPreviewResponse,
)
from app.services.promotion_service import (
    ASYNC_PROMOTION_THRESHOLD,
    build_promotion_preview,
    execute_promotion,
    get_promotion_job,
    queue_promotion_job,
)

router = APIRouter()


@router.get("", response_model=list[AcademicYearResponse])
async def list_years(_: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(AcademicYear).order_by(AcademicYear.start_date.desc()))
    years = list(rows.scalars().all())
    counts = dict(
        (
            await db.execute(
                select(StudentEnrollment.academic_year_id, func.count(StudentEnrollment.id))
                .group_by(StudentEnrollment.academic_year_id)
            )
        ).all()
    )
    return [
        AcademicYearResponse(
            id=year.id,
            school_id=year.school_id,
            name=year.name,
            start_date=year.start_date,
            end_date=year.end_date,
            is_current=year.is_current,
            created_at=year.created_at,
            enrollment_count=counts.get(year.id, 0),
        )
        for year in years
    ]


@router.get("/current", response_model=AcademicYearResponse)
async def get_current_year(_: object = Depends(require_any), db: AsyncSession = Depends(get_db)):
    year = (await db.execute(select(AcademicYear).where(AcademicYear.is_current == True))).scalar_one_or_none()
    if not year:
        raise HTTPException(status_code=404, detail="Current academic year not configured")
    return year


@router.post("", response_model=AcademicYearResponse)
async def create_year(payload: AcademicYearCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if payload.is_current:
        await db.execute(update(AcademicYear).where(AcademicYear.school_id == payload.school_id, AcademicYear.is_current == True).values(is_current=False))
    year = AcademicYear(**payload.model_dump())
    db.add(year)
    await db.commit()
    await db.refresh(year)
    return AcademicYearResponse.model_validate({**year.__dict__, "enrollment_count": 0})


@router.patch("/{year_id}", response_model=AcademicYearResponse)
async def update_year(year_id: UUID, payload: AcademicYearUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
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
    count = (
        await db.execute(
            select(func.count()).select_from(StudentEnrollment).where(StudentEnrollment.academic_year_id == year.id)
        )
    ).scalar_one() or 0
    return AcademicYearResponse.model_validate({**year.__dict__, "enrollment_count": count})


@router.post("/{year_id}/set-current", response_model=AcademicYearResponse)
async def set_current_year(year_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    year = (await db.execute(select(AcademicYear).where(AcademicYear.id == year_id))).scalar_one_or_none()
    if not year:
        raise HTTPException(status_code=404, detail="Academic year not found")
    await db.execute(update(AcademicYear).where(AcademicYear.school_id == year.school_id, AcademicYear.is_current == True).values(is_current=False))
    year.is_current = True
    await db.commit()
    await db.refresh(year)
    count = (
        await db.execute(
            select(func.count()).select_from(StudentEnrollment).where(StudentEnrollment.academic_year_id == year.id)
        )
    ).scalar_one() or 0
    return AcademicYearResponse.model_validate({**year.__dict__, "enrollment_count": count})


@router.delete("/{year_id}", response_model=MessageResponse)
async def delete_year(year_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    year = (await db.execute(select(AcademicYear).where(AcademicYear.id == year_id))).scalar_one_or_none()
    if not year:
        raise HTTPException(status_code=404, detail="Academic year not found")
    if year.is_current:
        raise HTTPException(status_code=400, detail="Cannot delete the active academic year")
    await db.delete(year)
    await db.commit()
    return MessageResponse(message="Academic year deleted")


@router.get("/{year_id}/promotion-preview", response_model=PromotionPreviewResponse)
async def promotion_preview(
    year_id: UUID,
    target_year_id: UUID = Query(...),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await build_promotion_preview(db, year_id, target_year_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{year_id}/promote", response_model=PromotionExecuteResponse)
async def promote_year(
    year_id: UUID,
    payload: PromotionExecuteRequest,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    preview = await build_promotion_preview(db, year_id, payload.target_year_id)
    generated_by = getattr(user, "id", None)

    if preview.total_active_students > ASYNC_PROMOTION_THRESHOLD:
        job = await queue_promotion_job(year_id, payload, generated_by)
        return PromotionExecuteResponse(job_id=job["job_id"], status="QUEUED")

    try:
        summary = await execute_promotion(db, year_id, payload, generated_by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PromotionExecuteResponse(status="COMPLETED", summary=summary)


@router.get("/{year_id}/promotion-job/{job_id}", response_model=PromotionJobStatus)
async def promotion_job_status(
    year_id: UUID,
    job_id: str,
    _: object = Depends(require_admin),
):
    try:
        data = await get_promotion_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PromotionJobStatus(
        job_id=job_id,
        status=data.get("status", "UNKNOWN"),
        progress=data.get("progress", 0),
        total=data.get("total", 0),
        summary=data.get("summary"),
        error=data.get("error"),
    )


@router.post("/{year_id}/rollover", response_model=MessageResponse)
async def rollover_year(year_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
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
