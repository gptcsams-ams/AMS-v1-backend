from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import Attendance
from app.models.attendance_window import AttendanceWindow
from app.models.student_enrollment import StudentEnrollment


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
    data_confidence: str = "HIGH",
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
        data_confidence=data_confidence,
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


async def finalize_window(
    db: AsyncSession,
    window_id: UUID,
    attendance_date: date,
    academic_year_id: UUID | None = None,
) -> dict:
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

    # Step 1: Update existing detection records — confirm PRESENT or downgrade to ABSENT
    records = (
        await db.execute(
            select(Attendance).where(
                Attendance.attendance_window_id == window_id,
                Attendance.attendance_date == attendance_date,
            )
        )
    ).scalars().all()

    present_count = 0
    absent_from_low_confidence = 0
    for row in records:
        if row.is_overridden:
            # Never touch manually overridden records
            continue
        if row.detection_count >= window.min_detections_required:
            row.status = "PRESENT"
            present_count += 1
        else:
            # Seen fewer times than required — not confident enough
            row.status = "ABSENT"
            absent_from_low_confidence += 1

    detected_student_ids = {r.student_id for r in records}

    # Step 2: Find all students enrolled in this section+year who were never detected.
    # Create ABSENT records for them so every enrolled student has an attendance entry.
    enrolled_rows = []
    if academic_year_id:
        enrolled_rows = (
            await db.execute(
                select(StudentEnrollment.student_id).where(
                    StudentEnrollment.section_id == window.section_id,
                    StudentEnrollment.academic_year_id == academic_year_id,
                    StudentEnrollment.status == "ACTIVE",
                )
            )
        ).scalars().all()

    absent_inserts = []
    for student_id in enrolled_rows:
        if student_id in detected_student_ids:
            continue
        absent_inserts.append({
            "student_id": student_id,
            "section_id": window.section_id,
            "academic_year_id": academic_year_id,
            "attendance_window_id": window_id,
            "attendance_date": attendance_date,
            "status": "ABSENT",
            "detection_count": 0,
            "data_confidence": "HIGH",
            "marked_by": "SYSTEM",
            "is_overridden": False,
        })

    if absent_inserts:
        await db.execute(
            insert(Attendance)
            .values(absent_inserts)
            .on_conflict_do_nothing(constraint="uq_student_window_date")
        )

    await db.commit()
    return {
        "status": "ok",
        "present": present_count,
        "absent_no_detection": len(absent_inserts),
        "absent_low_confidence": absent_from_low_confidence,
    }
