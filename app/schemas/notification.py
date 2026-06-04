from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class NotificationCreate(BaseModel):
    recipient_id: Optional[UUID] = None
    recipient_phone: Optional[str] = None
    recipient_email: Optional[str] = None
    channel: str
    trigger_type: str
    message: str


class NotificationUpdate(BaseModel):
    message: Optional[str] = None
    status: Optional[str] = None
