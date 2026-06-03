from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict


T = TypeVar("T")


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: Optional[dict] = None
    timestamp: datetime = datetime.utcnow()


class PaginatedResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: List[T]
    page: int
    page_size: int
    total: int


def error_payload(code: str, message: str, details: Optional[dict] = None) -> dict:
    return ErrorResponse(code=code, message=message, details=details).model_dump()
