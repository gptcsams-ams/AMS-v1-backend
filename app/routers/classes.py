from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, distinct, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin, require_any
from app.models.academic_record import AcademicRecord
from app.models.academic_class import AcademicClass
from app.models.attendance import Attendance
from app.models.attendance_window import AttendanceWindow
from app.models.camera import Camera
from app.models.camera_health_log import CameraHealthLog
from app.models.detection import Detection
from app.models.period_slot import PeriodSlot
from app.models.section import Section
from app.models.student_enrollment import StudentEnrollment
from app.models.teacher_subject_eligibility import TeacherSubjectEligibility
from app.models.timetable_entry import TimetableEntry
from app.models.timetable_frequency_target import TimetableFrequencyTarget
from app.schemas.classes import ClassCreate, ClassResponse, ClassUpdate
from app.schemas.common import MessageResponse
from app.schemas.section import SectionResponse

router = APIRouter()


@router.get("", response_model=list[ClassResponse])
async def list_classes(
    year_id: UUID | None = Query(None),
    include_sections: bool = Query(False),
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(
            AcademicClass,
            func.count(distinct(Section.id)).label("section_count"),
            func.count(distinct(StudentEnrollment.student_id)).label("student_count"),
        )
        .outerjoin(Section, Section.class_id == AcademicClass.id)
    )
    if year_id:
        query = query.outerjoin(
            StudentEnrollment,
            (StudentEnrollment.section_id == Section.id)
            & (StudentEnrollment.academic_year_id == year_id),
        )
    else:
        query = query.outerjoin(StudentEnrollment, StudentEnrollment.section_id == Section.id)
    rows = await db.execute(query.group_by(AcademicClass.id).order_by(AcademicClass.created_at.desc()))

    section_rows = []
    if include_sections:
        section_rows = list((await db.execute(select(Section).order_by(Section.name.asc()))).scalars().all())

    section_counts: dict = {}
    if year_id and include_sections:
        count_rows = (
            await db.execute(
                select(
                    StudentEnrollment.section_id,
                    func.count(distinct(StudentEnrollment.student_id)),
                )
                .where(StudentEnrollment.academic_year_id == year_id)
                .group_by(StudentEnrollment.section_id)
            )
        ).all()
        section_counts = {row[0]: row[1] for row in count_rows}

    results = []
    for row in rows:
        item = {
            "id": row.AcademicClass.id,
            "branch_id": row.AcademicClass.branch_id,
            "grade": row.AcademicClass.grade,
            "created_at": row.AcademicClass.created_at,
            "section_count": row.section_count,
            "student_count": row.student_count,
            "avg_attendance_pct": 0,
            "sections": None,
        }
        if include_sections:
            item["sections"] = [
                {
                    "id": section.id,
                    "class_id": section.class_id,
                    "name": section.name,
                    "student_count": section_counts.get(section.id, 0),
                }
                for section in section_rows
                if section.class_id == row.AcademicClass.id
            ]
        results.append(item)
    return results


@router.get("/{class_id}", response_model=ClassResponse)
async def get_class(
    class_id: UUID,
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(AcademicClass).where(AcademicClass.id == class_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Class not found")
    section_count = (await db.execute(
        select(func.count(Section.id)).where(Section.class_id == class_id)
    )).scalar_one()
    student_count = (await db.execute(
        select(func.count(distinct(StudentEnrollment.student_id)))
        .join(Section, Section.id == StudentEnrollment.section_id)
        .where(Section.class_id == class_id)
    )).scalar_one()
    return {
        "id": row.id,
        "branch_id": row.branch_id,
        "grade": row.grade,
        "created_at": row.created_at,
        "section_count": section_count,
        "student_count": student_count,
        "avg_attendance_pct": 0,
    }


@router.get("/{class_id}/sections", response_model=list[SectionResponse])
async def get_class_sections(
    class_id: UUID,
    _: object = Depends(require_any),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(select(Section).where(Section.class_id == class_id).order_by(Section.name.asc()))
    return list(rows.scalars().all())


@router.get("/{class_id}/attendance")
async def get_class_attendance(
    class_id: UUID,
    from_date: date = Query(...),
    to_date: date = Query(...),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    section_ids = (await db.execute(select(Section.id).where(Section.class_id == class_id))).scalars().all()
    if not section_ids:
        return []
    rows = await db.execute(
        select(Attendance).where(
            Attendance.section_id.in_(section_ids),
            Attendance.attendance_date >= from_date,
            Attendance.attendance_date <= to_date,
        )
    )
    return list(rows.scalars().all())


@router.post("", response_model=ClassResponse)
async def create_class(
    payload: ClassCreate,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(
        select(AcademicClass).where(
            AcademicClass.branch_id == payload.branch_id,
            AcademicClass.grade == payload.grade,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Grade '{payload.grade}' already exists for this branch")

    row = AcademicClass(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.patch("/{class_id}", response_model=ClassResponse)
async def update_class(
    class_id: UUID,
    payload: ClassUpdate,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(AcademicClass).where(AcademicClass.id == class_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Class not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{class_id}", response_model=MessageResponse)
async def delete_class(
    class_id: UUID,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(AcademicClass).where(AcademicClass.id == class_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Class not found")

    section_ids = list((await db.execute(
        select(Section.id).where(Section.class_id == class_id)
    )).scalars().all())

    if section_ids:
        camera_ids = list((await db.execute(
            select(Camera.id).where(Camera.section_id.in_(section_ids))
        )).scalars().all())

        period_slot_ids = list((await db.execute(
            select(PeriodSlot.id).where(PeriodSlot.section_id.in_(section_ids))
        )).scalars().all())

        await db.execute(
            update(AcademicRecord)
            .where(AcademicRecord.section_id.in_(section_ids))
            .values(section_id=None)
        )

        await db.execute(delete(StudentEnrollment).where(StudentEnrollment.section_id.in_(section_ids)))
        await db.execute(delete(Attendance).where(Attendance.section_id.in_(section_ids)))
        await db.execute(delete(Detection).where(Detection.section_id.in_(section_ids)))
        await db.execute(delete(TimetableFrequencyTarget).where(TimetableFrequencyTarget.section_id.in_(section_ids)))

        if period_slot_ids:
            await db.execute(delete(TimetableEntry).where(TimetableEntry.period_slot_id.in_(period_slot_ids)))
            await db.execute(delete(PeriodSlot).where(PeriodSlot.id.in_(period_slot_ids)))

        await db.execute(delete(AttendanceWindow).where(AttendanceWindow.section_id.in_(section_ids)))

        if camera_ids:
            await db.execute(delete(CameraHealthLog).where(CameraHealthLog.camera_id.in_(camera_ids)))
            await db.execute(delete(Camera).where(Camera.id.in_(camera_ids)))

        await db.execute(delete(Section).where(Section.id.in_(section_ids)))

    await db.execute(delete(TeacherSubjectEligibility).where(TeacherSubjectEligibility.class_id == class_id))
    await db.execute(delete(AcademicClass).where(AcademicClass.id == class_id))
    await db.commit()
    return MessageResponse(message="Class deleted")
