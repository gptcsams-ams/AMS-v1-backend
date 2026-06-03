from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models.student_enrollment import StudentEnrollment
from app.schemas.enrollment import EnrollmentCreate, EnrollmentResponse, EnrollmentUpdate

router = APIRouter(prefix="/enrollments")


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
    row = StudentEnrollment(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
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
