import json
from datetime import datetime

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.core.redis import get_redis
from app.schemas.mobile import MobileRegisterDeviceRequest, MobileRegisterDeviceResponse

router = APIRouter(prefix="/mobile")


@router.post("/register-device", response_model=MobileRegisterDeviceResponse)
async def register_device(payload: MobileRegisterDeviceRequest, user=Depends(get_current_user)):
    redis = get_redis()
    key = f"mobile:device:{user.id}:{payload.device_id}"
    now = datetime.utcnow()
    await redis.setex(
        key,
        60 * 60 * 24 * 90,
        json.dumps({
            "platform": payload.platform,
            "app_version": payload.app_version or "",
            "push_token": payload.push_token or "",
            "updated_at": now.isoformat()
        }),
    )
    return MobileRegisterDeviceResponse(registered=True, device_id=payload.device_id, updated_at=now)
