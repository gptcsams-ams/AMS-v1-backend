from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import Attendance
from app.models.attendance_window import AttendanceWindow


async def upsert_attendance(
    db: AsyncSession,
    *,
    student_id: UUID,
    section_id: UUID,
    academic_year_id: UUID,
    attendance_window_id: UUID,
    attendance_date: date,
    detected_at: datetime,
    status: str = "PRESENT",
    force: bool = False,
) -> None:
    # DB column is TIMESTAMP WITHOUT TIME ZONE — strip tzinfo if present
    if detected_at.tzinfo is not None:
        detected_at = detected_at.replace(tzinfo=None)

    stmt = insert(Attendance).values(
        student_id=student_id,
        section_id=section_id,
        academic_year_id=academic_year_id,
        attendance_window_id=attendance_window_id,
        attendance_date=attendance_date,
        status=status,
        detection_count=1,
        first_detected_at=detected_at,
        last_detected_at=detected_at,
        marked_by="SYSTEM",
        is_overridden=force,
    )
    update_set: dict = {
        "last_detected_at": detected_at,
        "first_detected_at": func.coalesce(Attendance.first_detected_at, detected_at),
        "status": status,
    }
    if force:
        # Manual override: always update regardless of is_overridden flag
        update_set["is_overridden"] = True
        update_set["marked_by"] = "MANUAL"
        stmt = stmt.on_conflict_do_update(
            constraint="uq_student_window_date",
            set_=update_set,
        )
    else:
        update_set["detection_count"] = func.greatest(Attendance.detection_count + 1, 1)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_student_window_date",
            set_=update_set,
            where=(Attendance.is_overridden == False),
        )
    await db.execute(stmt)
    await db.commit()


async def finalize_window(db: AsyncSession, window_id: UUID, attendance_date: date) -> dict:
    lock_key = abs(hash(f"{window_id}:{attendance_date.isoformat()}"))
    lock_sql = text("SELECT pg_try_advisory_xact_lock(:lock_key)")
    locked = (await db.execute(lock_sql, {"lock_key": lock_key})).scalar_one()
    if not locked:
        return {"status": "skipped", "reason": "window already finalizing"}

    window = (
        await db.execute(select(AttendanceWindow).where(AttendanceWindow.id == window_id))
    ).scalar_one_or_none()
    if not window:
        return {"status": "missing_window"}

    records = (
        await db.execute(
            select(Attendance).where(
                Attendance.attendance_window_id == window_id,
                Attendance.attendance_date == attendance_date,
            )
        )
    ).scalars().all()

    for row in records:
        if row.detection_count >= window.min_detections_required:
            if row.status not in ("PRESENT", "LATE"):
                row.status = "PRESENT"
        else:
            row.status = "ABSENT"

    await db.commit()
    return {"status": "ok", "processed": len(records)}
