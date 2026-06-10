from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.academic_year import AcademicYear
from app.models.attendance_window import AttendanceWindow
from app.models.camera import Camera
from cv_worker.section_worker import run_section_window

logger = logging.getLogger(__name__)

# key = "{window_id}:{YYYY-MM-DD}" → running asyncio.Task
_running: dict[str, asyncio.Task] = {}


async def _fetch_active_windows(today: date, now: datetime):
    """
    Return list of (AttendanceWindow, Camera, academic_year_id) for windows that:
      - are active
      - match today's weekday (days_of_week uses Python 0=Mon..6=Sun convention)
      - fall within their time range right now
      - have at least one active camera assigned to the section
    """
    weekday = today.weekday()
    results = []

    async with AsyncSessionLocal() as db:
        # Fetch the current academic year (one per school; take the first active one)
        year_row = (
            await db.execute(
                select(AcademicYear.id).where(AcademicYear.is_current == True).limit(1)
            )
        ).scalar_one_or_none()

        if year_row is None:
            logger.warning("No current academic year found — CV worker idle")
            return results

        year_id = year_row

        rows = await db.execute(
            select(AttendanceWindow, Camera)
            .join(Camera, Camera.section_id == AttendanceWindow.section_id)
            .where(
                AttendanceWindow.is_active == True,
                Camera.is_active == True,
                Camera.is_primary == True,
            )
        )

        for window, camera in rows.all():
            if weekday not in (window.days_of_week or []):
                continue
            # TODO: re-enable time window enforcement when ready
            # window_start = datetime.combine(today, window.start_time)
            # window_end = datetime.combine(today, window.end_time)
            # if now < window_start or now > window_end:
            #     continue
            results.append((window, camera, year_id))

    return results


async def _tick() -> None:
    today = date.today()
    now = datetime.now()

    # Clean up finished tasks
    done_keys = [k for k, t in _running.items() if t.done()]
    for k in done_keys:
        task = _running.pop(k)
        if not task.cancelled():
            exc = task.exception()
            if exc:
                logger.error("section_worker %s raised: %s", k, exc)

    try:
        active = await _fetch_active_windows(today, now)
    except Exception:
        logger.exception("Failed to fetch active windows")
        return

    for window, camera, year_id in active:
        key = f"{window.id}:{today.isoformat()}"
        if key in _running:
            continue  # already running

        logger.info("Spawning section_worker for window=%s camera=%s", window.id, camera.id)
        task = asyncio.create_task(
            run_section_window(
                window=window,
                camera=camera,
                academic_year_id=UUID(str(year_id)),
                attendance_date=today,
            ),
            name=f"section_worker:{key}",
        )
        _running[key] = task


async def run_scheduler() -> None:
    logger.info("CV scheduler started — polling every 30s")
    while True:
        try:
            await _tick()
        except Exception:
            logger.exception("Unexpected error in scheduler tick")
        await asyncio.sleep(30)
