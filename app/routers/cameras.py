from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin, require_super_admin
from app.models.camera import Camera
from app.models.camera_health_log import CameraHealthLog
from app.schemas.camera import CameraCreate, CameraUpdate
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/cameras")


@router.get("")
async def list_cameras(_: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return list((await db.execute(select(Camera))).scalars().all())


@router.get("/{camera_id}")
async def get_camera(camera_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Camera).where(Camera.id == camera_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")
    return row


@router.post("")
async def create_camera(payload: CameraCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = Camera(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": str(row.id)}


@router.patch("/{camera_id}")
async def update_camera(camera_id: UUID, payload: CameraUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Camera).where(Camera.id == camera_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    return {"message": "Camera updated"}


@router.delete("/{camera_id}", response_model=MessageResponse)
async def delete_camera(camera_id: UUID, _: object = Depends(require_super_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Camera).where(Camera.id == camera_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Camera deleted")


@router.get("/{camera_id}/health")
async def camera_health(camera_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return list((await db.execute(select(CameraHealthLog).where(CameraHealthLog.camera_id == camera_id))).scalars().all())
