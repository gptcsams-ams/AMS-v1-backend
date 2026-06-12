from collections import defaultdict
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin, require_any
from app.models.attendance import Attendance
from app.models.period_slot import PeriodSlot
from app.models.section import Section
from app.models.student import Student
from app.models.student_enrollment import StudentEnrollment
from app.models.student_face import StudentFace
from app.models.timetable_entry import TimetableEntry
from app.schemas.common import MessageResponse
from app.schemas.section import SectionCreate, SectionResponse, SectionUpdate

router = APIRouter()


@router.get("", response_model=list[SectionResponse])
async def list_sections(
    class_id: UUID | None = Query(default=None),
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Section)
    if class_id:
        stmt = stmt.where(Section.class_id == class_id)
    rows = await db.execute(stmt.order_by(Section.name.asc()))
    return list(rows.scalars().all())


@router.get("/{section_id}", response_model=SectionResponse)
async def get_section(
    section_id: UUID,
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(Section).where(Section.id == section_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Section not found")
    return row


@router.get("/{section_id}/students")
async def get_section_students(
    section_id: UUID,
    year_id: UUID | None = Query(default=None),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Student)
        .join(StudentEnrollment, StudentEnrollment.student_id == Student.id)
        .where(StudentEnrollment.section_id == section_id, Student.is_active == True)
    )
    if year_id:
        stmt = stmt.where(StudentEnrollment.academic_year_id == year_id)

    rows = await db.execute(
        stmt.order_by(Student.roll_number.asc(), Student.first_name.asc())
    )
    return list(rows.scalars().all())


@router.get("/{section_id}/attendance")
async def get_section_attendance_summary(
    section_id: UUID,
    year_id: UUID | None = Query(default=None),
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    now_time = datetime.now().time()

    # Total enrolled students in this section for the year
    enrolled_stmt = select(func.count()).select_from(StudentEnrollment).where(
        StudentEnrollment.section_id == section_id,
        StudentEnrollment.status == "ACTIVE",
    )
    if year_id:
        enrolled_stmt = enrolled_stmt.where(StudentEnrollment.academic_year_id == year_id)
    total: int = (await db.execute(enrolled_stmt)).scalar_one() or 0

    # Get all enrolled student ids
    enrolled_students_stmt = select(StudentEnrollment.student_id).where(
        StudentEnrollment.section_id == section_id,
        StudentEnrollment.status == "ACTIVE",
    )
    if year_id:
        enrolled_students_stmt = enrolled_students_stmt.where(
            StudentEnrollment.academic_year_id == year_id
        )
    enrolled_ids = list((await db.execute(enrolled_students_stmt)).scalars().all())

    # Today's present count
    today_att_stmt = select(func.count()).select_from(Attendance).where(
        Attendance.section_id == section_id,
        Attendance.attendance_date == today,
        Attendance.status == "PRESENT",
    )
    if year_id:
        today_att_stmt = today_att_stmt.where(Attendance.academic_year_id == year_id)
    today_present: int = (await db.execute(today_att_stmt)).scalar_one() or 0

    # Monthly attendance percentages (last 6 months)
    monthly_stmt = select(
        Attendance.attendance_date,
        Attendance.student_id,
        Attendance.status,
    ).where(Attendance.section_id == section_id)
    if year_id:
        monthly_stmt = monthly_stmt.where(Attendance.academic_year_id == year_id)
    att_rows = (await db.execute(monthly_stmt)).all()

    month_buckets: dict[str, dict] = defaultdict(lambda: {"present": 0, "total": 0})
    student_present_days: dict[str, int] = defaultdict(int)
    student_total_days: dict[str, set] = defaultdict(set)

    for row in att_rows:
        month_key = row.attendance_date.strftime("%Y-%m")
        month_buckets[month_key]["total"] += 1
        if row.status == "PRESENT":
            month_buckets[month_key]["present"] += 1
            student_present_days[str(row.student_id)] += 1
        student_total_days[str(row.student_id)].add(row.attendance_date)

    monthly = [
        {
            "month": datetime.strptime(m, "%Y-%m").strftime("%B"),
            "pct": round((v["present"] / v["total"] * 100) if v["total"] else 0, 1),
        }
        for m, v in sorted(month_buckets.items())
    ][-6:]

    # Month average (current calendar month)
    current_month = today.strftime("%Y-%m")
    cm = month_buckets.get(current_month, {"present": 0, "total": 0})
    month_avg = (cm["present"] / cm["total"] * 100) if cm["total"] else 0

    # Defaulters: students with < 75% attendance across all recorded days
    defaulter_count = 0
    for sid in enrolled_ids:
        sid_str = str(sid)
        days = student_total_days.get(sid_str, set())
        presents = student_present_days.get(sid_str, 0)
        if days and (presents / len(days)) < 0.75:
            defaulter_count += 1

    # Face not enrolled count
    face_not_enrolled = 0
    if enrolled_ids:
        enrolled_with_face_stmt = select(func.count(func.distinct(StudentFace.student_id))).where(
            StudentFace.student_id.in_(enrolled_ids),
            StudentFace.is_active == True,
        )
        with_face: int = (await db.execute(enrolled_with_face_stmt)).scalar_one() or 0
        face_not_enrolled = total - with_face

    # Current period
    current_period = None
    period_stmt = (
        select(PeriodSlot)
        .where(
            PeriodSlot.section_id == section_id,
            PeriodSlot.day_of_week == today.weekday(),
            PeriodSlot.start_time <= now_time,
            PeriodSlot.end_time >= now_time,
        )
        .limit(1)
    )
    slot = (await db.execute(period_stmt)).scalar_one_or_none()
    if slot:
        period_present_stmt = select(func.count()).select_from(Attendance).where(
            Attendance.section_id == section_id,
            Attendance.attendance_date == today,
            Attendance.status == "PRESENT",
        )
        period_present = (await db.execute(period_present_stmt)).scalar_one() or 0
        current_period = {
            "period_number": slot.period_number,
            "start_time": slot.start_time.strftime("%H:%M"),
            "end_time": slot.end_time.strftime("%H:%M"),
            "subject_name": "—",
            "teacher_name": "—",
            "present": period_present,
        }

    return {
        "total": total,
        "today_present": today_present,
        "month_avg": round(month_avg, 1),
        "defaulter_count": defaulter_count,
        "face_not_enrolled": face_not_enrolled,
        "monthly": monthly,
        "current_period": current_period,
    }


@router.get("/{section_id}/timetable")
async def get_section_timetable(
    section_id: UUID,
    year_id: UUID = Query(...),
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(TimetableEntry)
        .join(PeriodSlot, PeriodSlot.id == TimetableEntry.period_slot_id)
        .where(PeriodSlot.section_id == section_id, TimetableEntry.academic_year_id == year_id)
    )
    return list(rows.scalars().all())


@router.post("", response_model=SectionResponse)
async def create_section(
    payload: SectionCreate,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(
        select(Section).where(
            Section.class_id == payload.class_id,
            Section.name == payload.name,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Section '{payload.name}' already exists for this grade")

    row = Section(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.patch("/{section_id}", response_model=SectionResponse)
async def update_section(
    section_id: UUID,
    payload: SectionUpdate,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(Section).where(Section.id == section_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Section not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{section_id}", response_model=MessageResponse)
async def delete_section(
    section_id: UUID,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(Section).where(Section.id == section_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Section not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Section deleted")
