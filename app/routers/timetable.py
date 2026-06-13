from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin, require_any
from app.models.academic_class import AcademicClass
from app.models.attendance_window import AttendanceWindow
from app.models.period_slot import PeriodSlot
from app.models.section import Section
from app.models.subject import Subject
from app.models.teacher_profile import TeacherProfile
from app.models.teacher_subject_eligibility import TeacherSubjectEligibility
from app.models.timetable_entry import TimetableEntry
from app.models.timetable_frequency_target import TimetableFrequencyTarget
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.timetable import (
    FrequencyTargetCreate,
    PeriodSlotCreate,
    PeriodSlotUpdate,
    TimetableDayUpsert,
    TimetableEntryCreate,
    TimetableEntryUpdate,
)
from app.services.timetable_service import check_teacher_conflict, generate_draft, publish_timetable

router = APIRouter()

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def _entry_payload(entry: TimetableEntry) -> dict:
    slot = entry.period_slot
    teacher_user = entry.teacher.user if entry.teacher and entry.teacher.user else None
    return {
        "id": str(entry.id),
        "period_slot_id": str(entry.period_slot_id),
        "academic_year_id": str(entry.academic_year_id),
        "subject_id": str(entry.subject_id) if entry.subject_id else None,
        "teacher_profile_id": str(entry.teacher_profile_id) if entry.teacher_profile_id else None,
        "is_published": entry.is_published,
        "subject_name": entry.subject.name if entry.subject else None,
        "teacher_name": teacher_user.name if teacher_user else None,
        "slot": {
            "id": str(slot.id),
            "section_id": str(slot.section_id),
            "academic_year_id": str(slot.academic_year_id),
            "day_of_week": slot.day_of_week,
            "period_number": slot.period_number,
            "start_time": slot.start_time.isoformat(timespec="minutes"),
            "end_time": slot.end_time.isoformat(timespec="minutes"),
            "slot_type": slot.slot_type,
        },
    }


@router.get("/sections/{section_id}")
async def get_section_timetable(
    section_id: UUID,
    year_id: UUID | None = Query(default=None),
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    slot_stmt = select(PeriodSlot).where(PeriodSlot.section_id == section_id)
    entry_stmt = (
        select(TimetableEntry)
        .join(PeriodSlot, PeriodSlot.id == TimetableEntry.period_slot_id)
        .options(
            selectinload(TimetableEntry.period_slot),
            selectinload(TimetableEntry.subject),
            selectinload(TimetableEntry.teacher).selectinload(TeacherProfile.user),
        )
        .where(PeriodSlot.section_id == section_id)
    )
    if year_id:
        slot_stmt = slot_stmt.where(PeriodSlot.academic_year_id == year_id)
        entry_stmt = entry_stmt.where(TimetableEntry.academic_year_id == year_id)

    slots = list((await db.execute(slot_stmt.order_by(PeriodSlot.day_of_week, PeriodSlot.period_number))).scalars().all())
    rows = await db.execute(
        entry_stmt.order_by(PeriodSlot.day_of_week, PeriodSlot.period_number)
    )
    entries = list(rows.scalars().all())
    return {
        "slots": [
            {
                "id": str(slot.id),
                "section_id": str(slot.section_id),
                "academic_year_id": str(slot.academic_year_id),
                "day_of_week": slot.day_of_week,
                "period_number": slot.period_number,
                "start_time": slot.start_time.isoformat(timespec="minutes"),
                "end_time": slot.end_time.isoformat(timespec="minutes"),
                "slot_type": slot.slot_type,
            }
            for slot in slots
        ],
        "entries": [_entry_payload(entry) for entry in entries],
        "is_published": any(entry.is_published for entry in entries),
    }


@router.get("/overview")
async def get_timetable_overview(
    academic_year_id: UUID | None = Query(default=None),
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    class_rows = list((await db.execute(
        select(AcademicClass).order_by(AcademicClass.created_at.desc())
    )).scalars().all())
    if not class_rows:
        return []

    class_ids = [row.id for row in class_rows]
    section_rows = list((await db.execute(
        select(Section)
        .where(Section.class_id.in_(class_ids))
        .order_by(Section.name.asc())
    )).scalars().all())
    section_ids = [row.id for row in section_rows]

    total_periods: dict[UUID, int] = {}
    placed_periods: dict[UUID, int] = {}
    published: dict[UUID, bool] = {}

    if section_ids:
        slot_stmt = select(PeriodSlot.section_id, func.count(PeriodSlot.id)).where(PeriodSlot.section_id.in_(section_ids))
        entry_stmt = (
            select(
                PeriodSlot.section_id,
                func.count(TimetableEntry.id),
                func.bool_or(TimetableEntry.is_published),
            )
            .join(TimetableEntry, TimetableEntry.period_slot_id == PeriodSlot.id)
            .where(PeriodSlot.section_id.in_(section_ids))
        )
        if academic_year_id:
            slot_stmt = slot_stmt.where(PeriodSlot.academic_year_id == academic_year_id)
            entry_stmt = entry_stmt.where(TimetableEntry.academic_year_id == academic_year_id)
        slot_counts = await db.execute(slot_stmt.group_by(PeriodSlot.section_id))
        entry_counts = await db.execute(entry_stmt.group_by(PeriodSlot.section_id))
        total_periods = {section_id: count for section_id, count in slot_counts.all()}
        for section_id, count, is_published in entry_counts.all():
            placed_periods[section_id] = count
            published[section_id] = bool(is_published)

    sections_by_class: dict[UUID, list[Section]] = {}
    for section in section_rows:
        sections_by_class.setdefault(section.class_id, []).append(section)

    return [
        {
            "class_id": str(row.id),
            "grade": row.grade,
            "sections": [
                {
                    "section_id": str(section.id),
                    "name": section.name,
                    "is_published": published.get(section.id, False),
                    "total_periods": total_periods.get(section.id, 0),
                    "placed_periods": placed_periods.get(section.id, 0),
                    "homeroom_teacher": None,
                }
                for section in sections_by_class.get(row.id, [])
            ],
        }
        for row in class_rows
    ]


@router.get("/sections/{section_id}/days/{day_of_week}")
async def get_day_timetable(
    section_id: UUID,
    day_of_week: int,
    year_id: UUID = Query(...),
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(TimetableEntry)
        .join(PeriodSlot, PeriodSlot.id == TimetableEntry.period_slot_id)
        .options(
            selectinload(TimetableEntry.period_slot),
            selectinload(TimetableEntry.subject),
            selectinload(TimetableEntry.teacher).selectinload(TeacherProfile.user),
        )
        .where(
            PeriodSlot.section_id == section_id,
            PeriodSlot.academic_year_id == year_id,
            PeriodSlot.day_of_week == day_of_week,
        )
        .order_by(PeriodSlot.period_number)
    )
    return [_entry_payload(entry) for entry in rows.scalars().all()]


@router.put("/sections/{section_id}/days/{day_of_week}")
async def upsert_day_timetable(
    section_id: UUID,
    day_of_week: int,
    payload: TimetableDayUpsert,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing_slots = list((await db.execute(
        select(PeriodSlot).where(
            PeriodSlot.section_id == section_id,
            PeriodSlot.academic_year_id == payload.academic_year_id,
            PeriodSlot.day_of_week == day_of_week,
        )
    )).scalars().all())
    existing_slot_ids = [slot.id for slot in existing_slots]
    if existing_slot_ids:
        await db.execute(delete(TimetableEntry).where(TimetableEntry.period_slot_id.in_(existing_slot_ids)))
        await db.execute(delete(PeriodSlot).where(PeriodSlot.id.in_(existing_slot_ids)))
        await db.flush()

    for index, period in enumerate(payload.periods, start=1):
        slot = PeriodSlot(
            section_id=section_id,
            academic_year_id=payload.academic_year_id,
            day_of_week=day_of_week,
            period_number=period.period_number or index,
            start_time=period.start_time,
            end_time=period.end_time,
            slot_type=period.slot_type,
        )
        db.add(slot)
        await db.flush()
        db.add(TimetableEntry(
            period_slot_id=slot.id,
            academic_year_id=payload.academic_year_id,
            subject_id=period.subject_id if period.slot_type == "CLASS" else None,
            teacher_profile_id=period.teacher_profile_id if period.slot_type == "CLASS" else None,
        ))

    await db.commit()
    return {"message": f"{DAY_NAMES[day_of_week] if 0 <= day_of_week < 5 else 'Day'} saved"}


@router.get("/sections/{section_id}/eligible-teachers")
async def get_eligible_teachers(
    section_id: UUID,
    subject_id: UUID = Query(...),
    class_id: UUID = Query(...),
    day_of_week: int | None = Query(default=None),
    start_time: str | None = Query(default=None),
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(TeacherSubjectEligibility)
        .options(selectinload(TeacherSubjectEligibility.teacher).selectinload(TeacherProfile.user))
        .where(
            TeacherSubjectEligibility.subject_id == subject_id,
            TeacherSubjectEligibility.class_id == class_id,
        )
    )
    eligibilities = list(rows.scalars().all())
    teachers = [elig.teacher for elig in eligibilities if elig.teacher]

    if not teachers:
        section = (await db.execute(
            select(Section)
            .options(selectinload(Section.academic_class))
            .join(AcademicClass, AcademicClass.id == Section.class_id)
            .where(Section.id == section_id)
        )).scalar_one_or_none()
        teacher_stmt = select(TeacherProfile).options(selectinload(TeacherProfile.user))
        if section:
            teacher_stmt = teacher_stmt.where(TeacherProfile.branch_id == section.academic_class.branch_id)
        teacher_rows = await db.execute(teacher_stmt)
        teachers = list(teacher_rows.scalars().all())

    if not teachers:
        teacher_rows = await db.execute(
            select(TeacherProfile).options(selectinload(TeacherProfile.user))
        )
        teachers = list(teacher_rows.scalars().all())

    teacher_ids = [teacher.id for teacher in teachers]
    load_counts = {}
    if teacher_ids:
        counts = await db.execute(
            select(TimetableEntry.teacher_profile_id, func.count(TimetableEntry.id))
            .where(TimetableEntry.teacher_profile_id.in_(teacher_ids))
            .group_by(TimetableEntry.teacher_profile_id)
        )
        load_counts = {teacher_id: count for teacher_id, count in counts.all()}
    return [
        {
            "id": str(teacher.id),
            "name": teacher.user.name if teacher.user else "Teacher",
            "weekly_load": load_counts.get(teacher.id, 0),
            "busy": False,
        }
        for teacher in teachers
    ]


@router.get("/frequency-targets/{section_id}")
async def get_frequency_targets(section_id: UUID, year_id: UUID = Query(...), _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(TimetableFrequencyTarget).where(TimetableFrequencyTarget.section_id == section_id, TimetableFrequencyTarget.academic_year_id == year_id))
    return list(rows.scalars().all())


@router.post("/frequency-targets")
async def create_frequency_target(payload: FrequencyTargetCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = TimetableFrequencyTarget(**payload.model_dump())
    db.add(row)
    await db.commit()
    return {"id": str(row.id)}


@router.post("/period-slots")
async def create_period_slot(payload: PeriodSlotCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = PeriodSlot(**payload.model_dump())
    db.add(row)
    await db.commit()
    return {"id": str(row.id)}


@router.patch("/period-slots/{slot_id}")
async def update_period_slot(slot_id: UUID, payload: PeriodSlotUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(PeriodSlot).where(PeriodSlot.id == slot_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Period slot not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    return {"message": "Period slot updated"}


@router.delete("/period-slots/{slot_id}", response_model=MessageResponse)
async def delete_period_slot(slot_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(PeriodSlot).where(PeriodSlot.id == slot_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Period slot not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Period slot deleted")


@router.post("/entries")
async def create_entry(payload: TimetableEntryCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = TimetableEntry(**payload.model_dump())
    db.add(row)
    await db.commit()
    return {"id": str(row.id)}


@router.patch("/entries/{entry_id}")
async def update_entry(entry_id: UUID, payload: TimetableEntryUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(TimetableEntry).where(TimetableEntry.id == entry_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Entry not found")

    new_teacher_id = payload.teacher_profile_id if payload.teacher_profile_id is not None else row.teacher_profile_id
    if new_teacher_id and payload.teacher_profile_id is not None:
        slot = (await db.execute(
            select(PeriodSlot).where(PeriodSlot.id == row.period_slot_id)
        )).scalar_one_or_none()
        if slot:
            conflict = await check_teacher_conflict(
                db,
                teacher_profile_id=new_teacher_id,
                academic_year_id=row.academic_year_id,
                day_of_week=slot.day_of_week,
                start_time=slot.start_time,
                end_time=slot.end_time,
                exclude_entry_id=entry_id,
            )
            if conflict:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Teacher scheduling conflict",
                        "conflicting_entry_id": str(conflict.id),
                        "conflicting_slot_id": str(conflict.period_slot_id),
                    },
                )

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    return {"message": "Entry updated"}


@router.delete("/entries/{entry_id}", response_model=MessageResponse)
async def delete_entry(entry_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(TimetableEntry).where(TimetableEntry.id == entry_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Entry not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Entry deleted")


@router.post("/sections/{section_id}/generate-draft")
async def generate_draft_route(section_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await generate_draft(db, section_id)


@router.post("/sections/{section_id}/publish")
async def publish_route(section_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await publish_timetable(db, section_id)


@router.post("/sections/{section_id}/unpublish")
async def unpublish_route(section_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(TimetableEntry)
        .join(PeriodSlot, PeriodSlot.id == TimetableEntry.period_slot_id)
        .where(PeriodSlot.section_id == section_id)
    )).scalars().all()
    for row in rows:
        row.is_published = False
    await db.commit()
    return {"message": "Unpublished"}
