from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MobileRegisterDeviceRequest(BaseModel):
    device_id: str
    platform: str
    app_version: Optional[str] = None
    push_token: Optional[str] = None


class MobileRegisterDeviceResponse(BaseModel):
    registered: bool
    device_id: str
    updated_at: datetime
