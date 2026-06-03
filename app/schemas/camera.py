from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CameraCreate(BaseModel):
    section_id: UUID
    name: str
    room_number: str
    rtsp_url: str
    floor: Optional[str] = None
    building: Optional[str] = None
    location_description: Optional[str] = None
    is_active: bool = True
    is_primary: bool = True
    frame_sample_interval_secs: int = Field(default=30, ge=1)


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    room_number: Optional[str] = None
    rtsp_url: Optional[str] = None
    floor: Optional[str] = None
    building: Optional[str] = None
    location_description: Optional[str] = None
    is_active: Optional[bool] = None
    is_primary: Optional[bool] = None
    frame_sample_interval_secs: Optional[int] = Field(default=None, ge=1)
    stream_status: Optional[str] = None
