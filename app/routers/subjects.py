from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin, require_any, require_super_admin
from app.models.subject import Subject
from app.models.teacher_subject_eligibility import TeacherSubjectEligibility
from app.schemas.common import MessageResponse
from app.schemas.subject import SubjectCreate, SubjectResponse, SubjectUpdate

router = APIRouter(prefix="/subjects")


@router.get("", response_model=list[SubjectResponse])
async def list_subjects(
    branch_id: UUID | None = Query(default=None),
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Subject)
    if branch_id:
        stmt = stmt.where(Subject.branch_id == branch_id)
    rows = await db.execute(stmt.order_by(Subject.name.asc()))
    return list(rows.scalars().all())


@router.get("/{subject_id}", response_model=SubjectResponse)
async def get_subject(
    subject_id: UUID,
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(Subject).where(Subject.id == subject_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Subject not found")
    return row


@router.get("/{subject_id}/teachers")
async def get_subject_teachers(
    subject_id: UUID,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(TeacherSubjectEligibility).where(TeacherSubjectEligibility.subject_id == subject_id)
    )
    return list(rows.scalars().all())


@router.post("", response_model=SubjectResponse)
async def create_subject(
    payload: SubjectCreate,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = Subject(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.patch("/{subject_id}", response_model=SubjectResponse)
async def update_subject(
    subject_id: UUID,
    payload: SubjectUpdate,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(Subject).where(Subject.id == subject_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Subject not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{subject_id}", response_model=MessageResponse)
async def delete_subject(
    subject_id: UUID,
    _: object = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(Subject).where(Subject.id == subject_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Subject not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Subject deleted")
