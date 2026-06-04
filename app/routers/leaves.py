from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.models.leave_request import LeaveRequest
from app.schemas.leave import LeaveCreate, LeaveReview

router = APIRouter()
VALID_STATUSES = {"APPROVED", "REJECTED", "CANCELLED"}


@router.get("")
async def list_leaves(_: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(LeaveRequest).order_by(LeaveRequest.created_at.desc()))
    return list(rows.scalars().all())


@router.get("/{leave_id}")
async def get_leave(leave_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(LeaveRequest).where(LeaveRequest.id == leave_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Leave request not found")
    return row


@router.post("")
async def create_leave(payload: LeaveCreate, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = LeaveRequest(**payload.model_dump(), requested_by=user.id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": str(row.id)}


@router.patch("/{leave_id}/approve")
async def approve_leave(leave_id: UUID, payload: LeaveReview, user=Depends(get_current_user), _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail={"code": "INVALID_STATUS", "message": "Invalid leave status transition"})

    stmt = (
        update(LeaveRequest)
        .where(LeaveRequest.id == leave_id, LeaveRequest.version == payload.version)
        .values(
            status=payload.status,
            review_remarks=payload.review_remarks,
            reviewed_by=user.id,
            reviewed_at=func.now(),
            version=LeaveRequest.version + 1,
        )
    )
    res = await db.execute(stmt)
    if res.rowcount == 0:
        raise HTTPException(status_code=409, detail={"code": "OPTIMISTIC_LOCK_CONFLICT", "message": "Version mismatch"})
    await db.commit()
    return {"message": "Leave updated"}
