from datetime import date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.attendance_service import finalize_window


async def run_section_window(db: AsyncSession, window_id: UUID, on_date: date) -> dict:
    # Placeholder orchestration for CV worker pipeline.
    return await finalize_window(db, window_id, on_date)


def now_utc() -> datetime:
    return datetime.utcnow()
