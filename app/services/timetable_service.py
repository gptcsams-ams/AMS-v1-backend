from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_window import AttendanceWindow
from app.models.period_slot import PeriodSlot
from app.models.teacher_subject_eligibility import TeacherSubjectEligibility
from app.models.timetable_entry import TimetableEntry


async def check_teacher_conflict(
    db: AsyncSession,
    teacher_profile_id: UUID,
    academic_year_id: UUID,
    day_of_week: int,
    start_time,
    end_time,
    exclude_entry_id: UUID | None = None,
) -> TimetableEntry | None:
    """Return an existing TimetableEntry that conflicts with the given teacher/time window, or None."""
    stmt = (
        select(TimetableEntry)
        .join(PeriodSlot, PeriodSlot.id == TimetableEntry.period_slot_id)
        .where(
            TimetableEntry.teacher_profile_id == teacher_profile_id,
            TimetableEntry.academic_year_id == academic_year_id,
            PeriodSlot.day_of_week == day_of_week,
            # overlapping: slot starts before this one ends AND slot ends after this one starts
            PeriodSlot.start_time < end_time,
            PeriodSlot.end_time > start_time,
        )
    )
    if exclude_entry_id is not None:
        stmt = stmt.where(TimetableEntry.id != exclude_entry_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def generate_draft(db: AsyncSession, section_id: UUID) -> dict:
    slots = (await db.execute(select(PeriodSlot).where(PeriodSlot.section_id == section_id))).scalars().all()
    created = 0
    for slot in slots:
        exists = (await db.execute(select(TimetableEntry).where(TimetableEntry.period_slot_id == slot.id, TimetableEntry.academic_year_id == slot.academic_year_id))).scalar_one_or_none()
        if not exists:
            db.add(TimetableEntry(period_slot_id=slot.id, academic_year_id=slot.academic_year_id))
            created += 1
    await db.commit()
    return {"draft_entries_created": created}


async def validate_teacher_assignment(db: AsyncSession, teacher_profile_id: UUID, subject_id: UUID, class_id: UUID) -> bool:
    row = (await db.execute(
        select(TeacherSubjectEligibility).where(
            and_(
                TeacherSubjectEligibility.teacher_profile_id == teacher_profile_id,
                TeacherSubjectEligibility.subject_id == subject_id,
                TeacherSubjectEligibility.class_id == class_id,
            )
        )
    )).scalar_one_or_none()
    return row is not None


async def publish_timetable(db: AsyncSession, section_id: UUID) -> dict:
    rows = (await db.execute(
        select(TimetableEntry)
        .join(PeriodSlot, PeriodSlot.id == TimetableEntry.period_slot_id)
        .where(PeriodSlot.section_id == section_id)
    )).scalars().all()

    published = 0
    for entry in rows:
        if not entry.is_published:
            entry.is_published = True
            published += 1
        window_name = f"window-{entry.period_slot_id}"
        db.add(
            AttendanceWindow(
                section_id=section_id,
                timetable_entry_id=entry.id,
                name=window_name,
                start_time=entry.period_slot.start_time,
                end_time=entry.period_slot.end_time,
                days_of_week=[entry.period_slot.day_of_week],
                is_manual_trigger=False,
            )
        )
    await db.commit()
    return {"published_entries": published}
