from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin, require_super_admin
from app.models.branch import Branch
from app.schemas.branch import BranchCreate, BranchResponse, BranchUpdate
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/branches")


@router.get("", response_model=list[BranchResponse])
async def list_branches(
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Branch).order_by(Branch.created_at.desc()))
    return list(result.scalars().all())


@router.post("", response_model=BranchResponse)
async def create_branch(
    payload: BranchCreate,
    _: object = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    branch = Branch(**payload.model_dump())
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    return branch


@router.patch("/{branch_id}", response_model=BranchResponse)
async def update_branch(
    branch_id: UUID,
    payload: BranchUpdate,
    _: object = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    branch = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(branch, key, value)

    await db.commit()
    await db.refresh(branch)
    return branch


@router.delete("/{branch_id}", response_model=MessageResponse)
async def delete_branch(
    branch_id: UUID,
    _: object = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    branch = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    await db.delete(branch)
    await db.commit()
    return MessageResponse(message="Branch deleted")
