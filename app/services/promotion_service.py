import json
import re
import uuid
from collections import defaultdict
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic_class import AcademicClass
from app.models.academic_record import AcademicRecord
from app.models.academic_year import AcademicYear
from app.models.attendance import Attendance
from app.models.leave_request import LeaveRequest
from app.models.section import Section
from app.models.student import Student
from app.models.student_enrollment import StudentEnrollment
from app.schemas.promotion import (
    PromotionExecuteRequest,
    PromotionPreviewGradeMapping,
    PromotionPreviewResponse,
    PromotionPreviewSectionMapping,
    PromotionPreviewStudent,
    PromotionSummary,
)

LOW_ATTENDANCE_THRESHOLD = 75.0
ASYNC_PROMOTION_THRESHOLD = 500


def parse_grade_number(grade: str) -> Optional[int]:
    match = re.search(r"(\d+)", grade or "")
    return int(match.group(1)) if match else None


def suggest_next_grade(grade: str) -> str:
    num = parse_grade_number(grade)
    if num is None:
        return grade
    prefix = "Grade " if "grade" in grade.lower() else ""
    return f"{prefix}{num + 1}" if prefix else str(num + 1)


async def _student_attendance_pct(db: AsyncSession, student_id: UUID, year_id: UUID) -> Optional[float]:
    rows = (
        await db.execute(
            select(Attendance.attendance_date, Attendance.status).where(
                Attendance.student_id == student_id,
                Attendance.academic_year_id == year_id,
            )
        )
    ).all()
    if not rows:
        return None
    days: dict[date, str] = {}
    for row in rows:
        days[row.attendance_date] = row.status
    total = len(days)
    present = sum(1 for status in days.values() if status in ("PRESENT", "LATE", "EXCUSED"))
    return round(present / total * 100, 1) if total else None


async def build_promotion_preview(
    db: AsyncSession,
    source_year_id: UUID,
    target_year_id: UUID,
) -> PromotionPreviewResponse:
    source = (
        await db.execute(select(AcademicYear).where(AcademicYear.id == source_year_id))
    ).scalar_one_or_none()
    target = (
        await db.execute(select(AcademicYear).where(AcademicYear.id == target_year_id))
    ).scalar_one_or_none()
    if not source or not target:
        raise ValueError("Source or target academic year not found")

    enrollments = (
        await db.execute(
            select(StudentEnrollment, Student, Section, AcademicClass)
            .join(Student, Student.id == StudentEnrollment.student_id)
            .join(Section, Section.id == StudentEnrollment.section_id)
            .join(AcademicClass, AcademicClass.id == Section.class_id)
            .where(
                StudentEnrollment.academic_year_id == source_year_id,
                StudentEnrollment.status == "ACTIVE",
            )
        )
    ).all()

    all_classes = list((await db.execute(select(AcademicClass))).scalars().all())
    all_sections = list((await db.execute(select(Section))).scalars().all())
    classes_by_grade = {c.grade.strip().lower(): c for c in all_classes}
    sections_by_class: dict[UUID, list[Section]] = defaultdict(list)
    for section in all_sections:
        sections_by_class[section.class_id].append(section)

    existing_target = set(
        (
            await db.execute(
                select(StudentEnrollment.student_id).where(
                    StudentEnrollment.academic_year_id == target_year_id
                )
            )
        ).scalars().all()
    )

    pending_leave_count = (
        await db.execute(
            select(func.count())
            .select_from(LeaveRequest)
            .join(StudentEnrollment, StudentEnrollment.student_id == LeaveRequest.student_id)
            .where(
                StudentEnrollment.academic_year_id == source_year_id,
                StudentEnrollment.status == "ACTIVE",
                LeaveRequest.status == "PENDING",
            )
        )
    ).scalar_one() or 0

    grade_counts: dict[UUID, int] = defaultdict(int)
    section_counts: dict[UUID, int] = defaultdict(int)
    for en, _student, section, ac in enrollments:
        grade_counts[ac.id] += 1
        section_counts[section.id] += 1

    grade_mappings: list[PromotionPreviewGradeMapping] = []
    seen_classes: set[UUID] = set()
    for _en, _student, section, ac in enrollments:
        if ac.id in seen_classes:
            continue
        seen_classes.add(ac.id)
        suggested_grade = suggest_next_grade(ac.grade)
        suggested_class = classes_by_grade.get(suggested_grade.strip().lower())
        is_graduate = suggested_class is None and parse_grade_number(ac.grade) is not None
        grade_mappings.append(
            PromotionPreviewGradeMapping(
                source_class_id=ac.id,
                source_grade=ac.grade,
                student_count=grade_counts[ac.id],
                suggested_target_class_id=suggested_class.id if suggested_class else None,
                suggested_target_grade=suggested_grade if suggested_class else None,
                is_graduate=is_graduate,
                target_class_exists=suggested_class is not None,
            )
        )
    grade_mappings.sort(key=lambda item: parse_grade_number(item.source_grade) or 0)

    grade_to_target: dict[UUID, Optional[UUID]] = {}
    for gm in grade_mappings:
        grade_to_target[gm.source_class_id] = None if gm.is_graduate else gm.suggested_target_class_id

    section_mappings: list[PromotionPreviewSectionMapping] = []
    seen_sections: set[UUID] = set()
    for _en, _student, section, ac in enrollments:
        if section.id in seen_sections:
            continue
        seen_sections.add(section.id)
        target_class_id = grade_to_target.get(ac.id)
        target_section = None
        if target_class_id:
            for candidate in sections_by_class.get(target_class_id, []):
                if candidate.name.strip().lower() == section.name.strip().lower():
                    target_section = candidate
                    break
            if target_section is None:
                candidates = sections_by_class.get(target_class_id, [])
                target_section = candidates[0] if candidates else None
        section_mappings.append(
            PromotionPreviewSectionMapping(
                source_section_id=section.id,
                source_section_name=section.name,
                source_class_id=ac.id,
                source_grade=ac.grade,
                student_count=section_counts[section.id],
                suggested_target_section_id=target_section.id if target_section else None,
                suggested_target_section_name=target_section.name if target_section else None,
                target_class_id=target_class_id,
            )
        )

    students: list[PromotionPreviewStudent] = []
    for en, student, section, ac in enrollments:
        pct = await _student_attendance_pct(db, student.id, source_year_id)
        students.append(
            PromotionPreviewStudent(
                student_id=student.id,
                full_name=f"{student.first_name} {student.last_name}".strip(),
                roll_number=en.roll_number or student.roll_number,
                section_id=section.id,
                section_name=section.name,
                class_id=ac.id,
                grade=ac.grade,
                attendance_pct=pct,
                flagged_low_attendance=pct is not None and pct < LOW_ATTENDANCE_THRESHOLD,
                already_enrolled_in_target=student.id in existing_target,
                source_status=en.status,
            )
        )

    duplicate_count = sum(1 for student in students if student.already_enrolled_in_target)

    return PromotionPreviewResponse(
        source_year_id=source.id,
        source_year_name=source.name,
        target_year_id=target.id,
        target_year_name=target.name,
        grade_mappings=grade_mappings,
        section_mappings=section_mappings,
        students=students,
        total_active_students=len(students),
        duplicate_enrollment_count=duplicate_count,
        pending_leave_count=pending_leave_count,
        low_attendance_threshold=LOW_ATTENDANCE_THRESHOLD,
    )


async def _create_academic_record(
    db: AsyncSession,
    enrollment: StudentEnrollment,
    student_id: UUID,
    year_id: UUID,
    section_id: UUID,
    promotion_status: str,
    generated_by: Optional[UUID],
) -> None:
    existing = (
        await db.execute(
            select(AcademicRecord).where(
                AcademicRecord.student_id == student_id,
                AcademicRecord.academic_year_id == year_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return

    pct = await _student_attendance_pct(db, student_id, year_id)
    days_rows = (
        await db.execute(
            select(Attendance.attendance_date, Attendance.status).where(
                Attendance.student_id == student_id,
                Attendance.academic_year_id == year_id,
            )
        )
    ).all()
    unique_days = {row.attendance_date for row in days_rows}
    present_days = sum(
        1
        for row in days_rows
        if row.status in ("PRESENT", "LATE", "EXCUSED")
    )

    db.add(
        AcademicRecord(
            student_id=student_id,
            academic_year_id=year_id,
            section_id=section_id,
            promotion_status=promotion_status,
            final_attendance_pct=pct,
            total_present=present_days,
            total_working_days=len(unique_days),
            subject_attendance={},
            generated_by=generated_by,
        )
    )


async def execute_promotion(
    db: AsyncSession,
    source_year_id: UUID,
    payload: PromotionExecuteRequest,
    generated_by: Optional[UUID],
) -> PromotionSummary:
    source = (
        await db.execute(select(AcademicYear).where(AcademicYear.id == source_year_id))
    ).scalar_one_or_none()
    target = (
        await db.execute(select(AcademicYear).where(AcademicYear.id == payload.target_year_id))
    ).scalar_one_or_none()
    if not source or not target:
        raise ValueError("Source or target academic year not found")

    grade_map = {item.source_class_id: item for item in payload.grade_mappings}
    section_map = {item.source_section_id: item.target_section_id for item in payload.section_mappings}
    override_map = {item.student_id: item for item in payload.student_overrides}

    enrollments = (
        await db.execute(
            select(StudentEnrollment)
            .where(
                StudentEnrollment.academic_year_id == source_year_id,
                StudentEnrollment.status == "ACTIVE",
            )
        )
    ).scalars().all()

    summary = PromotionSummary(
        total_reviewed=0,
        promoted=0,
        detained=0,
        transferred=0,
        graduated=0,
        skipped_already_enrolled=0,
        academic_records_created=0,
    )

    for enrollment in enrollments:
        summary.total_reviewed += 1
        student_id = enrollment.student_id

        exists = (
            await db.execute(
                select(StudentEnrollment).where(
                    StudentEnrollment.student_id == student_id,
                    StudentEnrollment.academic_year_id == payload.target_year_id,
                )
            )
        ).scalar_one_or_none()
        if exists:
            summary.skipped_already_enrolled += 1
            continue

        section = (
            await db.execute(select(Section).where(Section.id == enrollment.section_id))
        ).scalar_one_or_none()
        if not section:
            continue
        ac = (
            await db.execute(select(AcademicClass).where(AcademicClass.id == section.class_id))
        ).scalar_one_or_none()
        if not ac:
            continue

        override = override_map.get(student_id)
        grade_mapping = grade_map.get(ac.id)

        if override and override.action in ("TRANSFER", "WITHDRAW"):
            await _create_academic_record(
                db, enrollment, student_id, source_year_id, section.id, "WITHDRAWN", generated_by
            )
            summary.academic_records_created += 1
            enrollment.status = "WITHDRAWN"
            enrollment.exited_at = date.today()
            await db.execute(
                update(Student).where(Student.id == student_id).values(is_active=False)
            )
            summary.transferred += 1
            continue

        if override and override.action == "DETAIN":
            detain_section_id = override.target_section_id or enrollment.section_id
            await _create_academic_record(
                db, enrollment, student_id, source_year_id, section.id, "DETAINED", generated_by
            )
            summary.academic_records_created += 1
            enrollment.status = "DETAINED"
            enrollment.exited_at = date.today()
            db.add(
                StudentEnrollment(
                    student_id=student_id,
                    section_id=detain_section_id,
                    academic_year_id=payload.target_year_id,
                    roll_number=enrollment.roll_number,
                    status="ACTIVE",
                    enrolled_at=target.start_date,
                )
            )
            summary.detained += 1
            continue

        if grade_mapping and grade_mapping.is_graduate:
            await _create_academic_record(
                db, enrollment, student_id, source_year_id, section.id, "PROMOTED", generated_by
            )
            summary.academic_records_created += 1
            enrollment.status = "PROMOTED"
            enrollment.exited_at = date.today()
            await db.execute(
                update(Student).where(Student.id == student_id).values(is_active=False)
            )
            summary.graduated += 1
            continue

        target_section_id = section_map.get(enrollment.section_id)
        if not target_section_id and grade_mapping and grade_mapping.target_class_id:
            candidates = (
                await db.execute(
                    select(Section).where(Section.class_id == grade_mapping.target_class_id)
                )
            ).scalars().all()
            for candidate in candidates:
                if candidate.name.strip().lower() == section.name.strip().lower():
                    target_section_id = candidate.id
                    break
            if not target_section_id and candidates:
                target_section_id = candidates[0].id

        if not target_section_id:
            summary.skipped_already_enrolled += 1
            continue

        await _create_academic_record(
            db, enrollment, student_id, source_year_id, section.id, "PROMOTED", generated_by
        )
        summary.academic_records_created += 1
        enrollment.status = "PROMOTED"
        enrollment.exited_at = date.today()
        db.add(
            StudentEnrollment(
                student_id=student_id,
                section_id=target_section_id,
                academic_year_id=payload.target_year_id,
                roll_number=enrollment.roll_number,
                status="ACTIVE",
                enrolled_at=target.start_date,
            )
        )
        summary.promoted += 1

    await db.commit()
    return summary


async def queue_promotion_job(
    source_year_id: UUID,
    payload: PromotionExecuteRequest,
    generated_by: Optional[UUID],
) -> dict:
    from app.tasks.promotion_tasks import run_promotion

    job_id = str(uuid.uuid4())
    redis = __import__("app.core.redis", fromlist=["get_redis"]).get_redis()
    key = f"promotion_job:{job_id}"
    initial = {
        "status": "QUEUED",
        "progress": 0,
        "total": 0,
        "summary": None,
        "error": None,
        "updated_at": datetime.utcnow().isoformat(),
    }
    await redis.setex(key, 7200, json.dumps(initial))
    run_promotion.delay(
        job_id,
        str(source_year_id),
        payload.model_dump(mode="json"),
        str(generated_by) if generated_by else None,
    )
    return {"job_id": job_id, "status": "QUEUED"}


async def get_promotion_job(job_id: str) -> dict:
    redis = __import__("app.core.redis", fromlist=["get_redis"]).get_redis()
    raw = await redis.get(f"promotion_job:{job_id}")
    if not raw:
        raise ValueError("Promotion job not found")
    return json.loads(raw)
