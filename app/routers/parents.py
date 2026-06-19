from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models.parent import Parent
from app.models.student_parent import StudentParent
from app.schemas.common import MessageResponse
from app.schemas.parent import ParentCreate, ParentResponse, ParentStudentLinkCreate, ParentUpdate

router = APIRouter()


@router.get("", response_model=list[ParentResponse])
async def list_parents(search: str | None = Query(default=None), _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    stmt = select(Parent)
    if search:
        stmt = stmt.where(or_(Parent.full_name.ilike(f"%{search}%"), Parent.contact_number.ilike(f"%{search}%")))
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.get("/{parent_id}", response_model=ParentResponse)
async def get_parent(parent_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Parent).where(Parent.id == parent_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Parent not found")
    return row


@router.get("/{parent_id}/children")
async def get_children(parent_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(StudentParent).where(StudentParent.parent_id == parent_id))
    return list(rows.scalars().all())


@router.post("", response_model=ParentResponse)
async def create_parent(payload: ParentCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = Parent(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.patch("/{parent_id}", response_model=ParentResponse)
async def update_parent(parent_id: UUID, payload: ParentUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Parent).where(Parent.id == parent_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Parent not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{parent_id}", response_model=MessageResponse)
async def delete_parent(parent_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Parent).where(Parent.id == parent_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Parent not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Parent deleted")


@router.post("/{parent_id}/link-student", response_model=MessageResponse)
async def link_student(parent_id: UUID, payload: ParentStudentLinkCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = StudentParent(parent_id=parent_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    return MessageResponse(message="Student linked")


@router.delete("/{parent_id}/students/{student_id}", response_model=MessageResponse)
async def unlink_student(parent_id: UUID, student_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(StudentParent).where(StudentParent.parent_id == parent_id, StudentParent.student_id == student_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Student unlinked")
