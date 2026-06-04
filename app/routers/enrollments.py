from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models.student_enrollment import StudentEnrollment
from app.schemas.common import MessageResponse
from app.schemas.enrollment import EnrollmentCreate, EnrollmentResponse, EnrollmentUpdate

router = APIRouter()


@router.get("", response_model=list[EnrollmentResponse])
async def list_enrollments(
    year_id: UUID | None = Query(default=None),
    section_id: UUID | None = Query(default=None),
    student_id: UUID | None = Query(default=None),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(StudentEnrollment)
    if year_id:
        stmt = stmt.where(StudentEnrollment.academic_year_id == year_id)
    if section_id:
        stmt = stmt.where(StudentEnrollment.section_id == section_id)
    if student_id:
        stmt = stmt.where(StudentEnrollment.student_id == student_id)
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.post("", response_model=EnrollmentResponse)
async def create_enrollment(payload: EnrollmentCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    existing_student_year = (await db.execute(
        select(StudentEnrollment).where(
            StudentEnrollment.student_id == payload.student_id,
            StudentEnrollment.academic_year_id == payload.academic_year_id,
        )
    )).scalar_one_or_none()
    if existing_student_year:
        raise HTTPException(
            status_code=409,
            detail="This student is already enrolled for the selected academic year.",
        )

    existing_roll = (await db.execute(
        select(StudentEnrollment).where(
            StudentEnrollment.section_id == payload.section_id,
            StudentEnrollment.academic_year_id == payload.academic_year_id,
            StudentEnrollment.roll_number == payload.roll_number,
        )
    )).scalar_one_or_none()
    if existing_roll:
        raise HTTPException(
            status_code=409,
            detail=f"Roll number '{payload.roll_number}' already exists in this section for the selected academic year.",
        )

    row = StudentEnrollment(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/{enrollment_id}", response_model=EnrollmentResponse)
async def get_enrollment(enrollment_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(StudentEnrollment).where(StudentEnrollment.id == enrollment_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return row


@router.patch("/{enrollment_id}", response_model=EnrollmentResponse)
async def update_enrollment(enrollment_id: UUID, payload: EnrollmentUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(StudentEnrollment).where(StudentEnrollment.id == enrollment_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{enrollment_id}", response_model=MessageResponse)
async def delete_enrollment(enrollment_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(StudentEnrollment).where(StudentEnrollment.id == enrollment_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Enrollment deleted")
