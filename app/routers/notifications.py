from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.models.notification import Notification
from app.schemas.notification import NotificationCreate

router = APIRouter(prefix="/notifications")


@router.get("")
async def list_notifications(_: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return list((await db.execute(select(Notification))).scalars().all())


@router.get("/parent")
async def list_parent_notifications(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role != "PARENT":
        raise HTTPException(status_code=403, detail="Only parents can access this endpoint")
    rows = await db.execute(
        select(Notification)
        .where(Notification.recipient_id == current_user.id)
        .order_by(Notification.created_at.desc())
    )
    return list(rows.scalars().all())


@router.post("")
async def create_notification(payload: NotificationCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = Notification(**payload.model_dump())
    db.add(row)
    await db.commit()
    return {"id": str(row.id)}


@router.get("/{notification_id}")
async def get_notification(notification_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Notification).where(Notification.id == notification_id))).scalar_one_or_none()
