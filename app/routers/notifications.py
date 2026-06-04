from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models.notification import Notification
from app.schemas.common import MessageResponse
from app.schemas.notification import NotificationCreate, NotificationUpdate

router = APIRouter()


@router.get("")
async def list_notifications(_: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return list((await db.execute(select(Notification))).scalars().all())


@router.post("")
async def create_notification(payload: NotificationCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = Notification(**payload.model_dump())
    db.add(row)
    await db.commit()
    return {"id": str(row.id)}


@router.get("/{notification_id}")
async def get_notification(notification_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Notification).where(Notification.id == notification_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Notification not found")
    return row


@router.patch("/{notification_id}")
async def update_notification(notification_id: UUID, payload: NotificationUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Notification).where(Notification.id == notification_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Notification not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{notification_id}", response_model=MessageResponse)
async def delete_notification(notification_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Notification).where(Notification.id == notification_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Notification not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Notification deleted")
