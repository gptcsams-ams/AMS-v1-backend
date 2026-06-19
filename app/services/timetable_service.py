from datetime import time, timedelta, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic_class import AcademicClass
from app.models.attendance_window import AttendanceWindow
from app.models.period_slot import PeriodSlot
from app.models.section import Section
from app.models.subject import Subject
from app.models.teacher_profile import TeacherProfile
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


def _add_minutes(t: time, minutes: int) -> time:
    dt = datetime(2000, 1, 1, t.hour, t.minute) + timedelta(minutes=minutes)
    return dt.time()


async def auto_generate_all(db: AsyncSession, branch_id: UUID, year_id: UUID) -> dict:
    """
    Generate conflict-free timetables for every section in a branch.

    Schedule (Mon-Fri):
      08:00  P1 (40 min)
      08:40  P2 (40 min)
      09:20  P3 (40 min)
      10:00  BREAK 15 min
      10:15  P4 (40 min)
      10:55  P5 (40 min)
      11:35  P6 (40 min)
      12:15  BREAK 15 min
      12:30  P7 (40 min)
      13:10  P8 (40 min)

    Teacher conflict: no two sections share the same teacher at the same day+time.
    """
    PERIOD_DURATION = 40
    BREAK_DURATION = 15
    DAYS = [0, 1, 2, 3, 4]  # Mon-Fri
    DAY_START = time(8, 0)

    # Build period+break schedule template (times only, same every day)
    schedule_template: list[dict] = []
    current = DAY_START
    period_count = 0
    total_periods = 8

    while period_count < total_periods:
        period_count += 1
        end = _add_minutes(current, PERIOD_DURATION)
        schedule_template.append({"slot_type": "CLASS", "start": current, "end": end, "period_num": period_count})
        current = end
        # Insert 15-min break after every 3rd period
        if period_count % 3 == 0 and period_count < total_periods:
            break_end = _add_minutes(current, BREAK_DURATION)
            schedule_template.append({"slot_type": "BREAK", "start": current, "end": break_end, "period_num": None})
            current = break_end

    # Load all sections in branch
    section_rows = list((await db.execute(
        select(Section)
        .join(AcademicClass, AcademicClass.id == Section.class_id)
        .where(AcademicClass.branch_id == branch_id)
        .order_by(AcademicClass.grade, Section.name)
    )).scalars().all())

    if not section_rows:
        return {"sections_generated": 0, "total_periods": 0}

    # Load subjects for branch
    subjects = list((await db.execute(
        select(Subject).where(Subject.branch_id == branch_id)
    )).scalars().all())

    # Load all teacher profiles for branch
    teachers = list((await db.execute(
        select(TeacherProfile).where(TeacherProfile.branch_id == branch_id)
    )).scalars().all())

    # Track which teachers are assigned per (day, start_time) — conflict guard
    # teacher_busy[teacher_id][(day, start_time)] = True
    teacher_busy: dict = {}

    from sqlalchemy import text as _text

    section_ids = [str(s.id) for s in section_rows]
    yid = str(year_id)

    # Delete all existing data for every section in one transaction
    for sid in section_ids:
        await db.execute(_text(
            "DELETE FROM timetable_entries WHERE period_slot_id IN "
            "(SELECT id FROM period_slots WHERE section_id = :sid AND academic_year_id = :yid)"
        ), {"sid": sid, "yid": yid})
        await db.execute(_text(
            "DELETE FROM period_slots WHERE section_id = :sid AND academic_year_id = :yid"
        ), {"sid": sid, "yid": yid})
    await db.commit()

    all_slots: list[PeriodSlot] = []
    all_entries: list[TimetableEntry] = []
    total_created = 0

    for section in section_rows:
        subject_cycle_index = 0
        for day in DAYS:
            for slot_index, slot_def in enumerate(schedule_template, start=1):
                slot_id = uuid4()
                all_slots.append(PeriodSlot(
                    id=slot_id,
                    section_id=section.id,
                    academic_year_id=year_id,
                    day_of_week=day,
                    period_number=slot_index,
                    start_time=slot_def["start"],
                    end_time=slot_def["end"],
                    slot_type=slot_def["slot_type"],
                ))

                chosen_subject_id = None
                chosen_teacher_id = None

                if slot_def["slot_type"] == "CLASS" and subjects:
                    subj = subjects[subject_cycle_index % len(subjects)]
                    subject_cycle_index += 1
                    chosen_subject_id = subj.id

                    for teacher in teachers:
                        key = (teacher.id, day, slot_def["start"])
                        if not teacher_busy.get(key):
                            chosen_teacher_id = teacher.id
                            teacher_busy[key] = True
                            break

                all_entries.append(TimetableEntry(
                    period_slot_id=slot_id,
                    academic_year_id=year_id,
                    subject_id=chosen_subject_id,
                    teacher_profile_id=chosen_teacher_id,
                ))
                total_created += 1

    # Single bulk insert for all sections — 2 round-trips total
    db.add_all(all_slots)
    db.add_all(all_entries)
    await db.commit()

    return {"sections_generated": len(section_rows), "total_periods": total_created}


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
