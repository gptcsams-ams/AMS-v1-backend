import asyncio
from datetime import date

from app.core.database import AsyncSessionLocal
from app.models.attendance_window import AttendanceWindow
from app.services.attendance_service import finalize_window


async def tick() -> None:
    async with AsyncSessionLocal() as db:
        windows = (await db.execute(AttendanceWindow.__table__.select().where(AttendanceWindow.is_active == True))).all()
        today = date.today()
        for row in windows:
            await finalize_window(db, row.id, today)


async def run_scheduler() -> None:
    while True:
        await tick()
        await asyncio.sleep(60)
