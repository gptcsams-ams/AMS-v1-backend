from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_teacher
from app.models.notification import Notification
from app.models.parent import Parent
from app.models.ptm_record import PTMRecord
from app.models.section import Section
from app.models.student import Student
from app.models.student_enrollment import StudentEnrollment
from app.models.student_parent import StudentParent
from app.models.teacher_profile import TeacherProfile
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.ptm import PTMInitiateRequest, PTMRecordCreate, PTMRecordResponse, PTMRecordUpdate

router = APIRouter()

PTM_LOAD = (
    selectinload(PTMRecord.student),
    selectinload(PTMRecord.parent),
    selectinload(PTMRecord.teacher).selectinload(TeacherProfile.user),
    selectinload(PTMRecord.section).selectinload(Section.academic_class),
)


def _serialize(row: PTMRecord) -> PTMRecordResponse:
    student_name = None
    if row.student:
        student_name = f"{row.student.first_name} {row.student.last_name}".strip()
    class_name = None
    if row.section and row.section.academic_class:
        class_name = f"{row.section.academic_class.grade}-{row.section.name}"
    return PTMRecordResponse(
        id=row.id,
        student_id=row.student_id,
        parent_id=row.parent_id,
        teacher_id=row.teacher_id,
        section_id=row.section_id,
        meeting_date=row.meeting_date,
        meeting_time=row.meeting_time,
        discussion=row.discussion,
        action_taken=row.action_taken,
        status=row.status,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        student_name=student_name,
        parent_name=row.parent.full_name if row.parent else None,
        teacher_name=row.teacher.user.name if row.teacher and row.teacher.user else None,
        class_name=class_name,
    )


async def _get_parent_for_user(db: AsyncSession, user: User) -> Parent:
    parent = (
        await db.execute(select(Parent).where(Parent.user_id == user.id))
    ).scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent profile not found")
    return parent


@router.get("", response_model=list[PTMRecordResponse])
async def list_ptm_records(
    student_id: UUID | None = Query(default=None),
    _: object = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(PTMRecord)
        .options(*PTM_LOAD)
        .order_by(PTMRecord.meeting_date.desc(), PTMRecord.created_at.desc())
    )
    if student_id:
        stmt = stmt.where(PTMRecord.student_id == student_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [_serialize(row) for row in rows]


@router.get("/parent", response_model=list[PTMRecordResponse])
async def list_parent_ptm_records(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "PARENT":
        raise HTTPException(status_code=403, detail="Only parents can access this endpoint")

    parent = await _get_parent_for_user(db, current_user)
    child_ids = select(StudentParent.student_id).where(StudentParent.parent_id == parent.id)
    rows = (
        await db.execute(
            select(PTMRecord)
            .options(*PTM_LOAD)
            .where(PTMRecord.student_id.in_(child_ids))
            .order_by(PTMRecord.meeting_date.desc(), PTMRecord.created_at.desc())
        )
    ).scalars().all()
    return [_serialize(row) for row in rows]


@router.post("", response_model=PTMRecordResponse)
async def create_ptm_record(
    payload: PTMRecordCreate,
    current_user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    student = (
        await db.execute(select(Student).where(Student.id == payload.student_id))
    ).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    row = PTMRecord(**payload.model_dump(), created_by=current_user.id)
    db.add(row)
    await db.commit()
    row = (
        await db.execute(select(PTMRecord).options(*PTM_LOAD).where(PTMRecord.id == row.id))
    ).scalar_one()
    return _serialize(row)


@router.post("/initiate")
async def initiate_ptm(
    payload: PTMInitiateRequest,
    current_user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    section = (
        await db.execute(
            select(Section)
            .options(selectinload(Section.academic_class))
            .where(Section.id == payload.section_id)
        )
    ).scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Class section not found")

    enrollment_rows = (
        await db.execute(
            select(StudentEnrollment)
            .options(
                selectinload(StudentEnrollment.student)
                .selectinload(Student.student_parents)
                .selectinload(StudentParent.parent)
                .selectinload(Parent.user),
            )
            .where(
                StudentEnrollment.section_id == payload.section_id,
                StudentEnrollment.status == "ACTIVE",
            )
        )
    ).scalars().all()
    if not enrollment_rows:
        raise HTTPException(status_code=400, detail="No active students found for the selected class")

    class_name = f"{section.academic_class.grade}-{section.name}" if section.academic_class else section.name
    created_records = 0
    created_notifications = 0

    for enrollment in enrollment_rows:
        student = enrollment.student
        if not student:
            continue
        links = student.student_parents or []
        if not links:
            record = PTMRecord(
                student_id=student.id,
                section_id=section.id,
                meeting_date=payload.meeting_date,
                meeting_time=payload.meeting_time,
                discussion=payload.message,
                action_taken="Pending discussion",
                status="SCHEDULED",
                created_by=current_user.id,
            )
            db.add(record)
            created_records += 1
            continue

        for link in links:
            record = PTMRecord(
                student_id=student.id,
                parent_id=link.parent_id,
                section_id=section.id,
                meeting_date=payload.meeting_date,
                meeting_time=payload.meeting_time,
                discussion=payload.message,
                action_taken="Pending discussion",
                status="SCHEDULED",
                created_by=current_user.id,
            )
            db.add(record)
            await db.flush()
            created_records += 1

            parent_user = link.parent.user if link.parent else None
            if parent_user:
                student_name = f"{student.first_name} {student.last_name}".strip()
                message = (
                    f"PTM scheduled for {student_name} ({class_name}) on "
                    f"{payload.meeting_date.isoformat()} at {payload.meeting_time.strftime('%H:%M')}. "
                    f"{payload.message}"
                )
                db.add(Notification(
                    recipient_id=parent_user.id,
                    recipient_phone=link.parent.contact_number if link.parent else None,
                    recipient_email=link.parent.email if link.parent else None,
                    channel="PUSH",
                    trigger_type="PTM",
                    reference_id=record.id,
                    reference_type="PTM_RECORD",
                    message=message,
                    status="DELIVERED",
                ))
                created_notifications += 1

    await db.commit()
    return {
        "message": "PTM initiated",
        "records_created": created_records,
        "notifications_created": created_notifications,
    }


@router.patch("/{ptm_id}", response_model=PTMRecordResponse)
async def update_ptm_record(
    ptm_id: UUID,
    payload: PTMRecordUpdate,
    _: object = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(select(PTMRecord).where(PTMRecord.id == ptm_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="PTM record not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    row = (
        await db.execute(select(PTMRecord).options(*PTM_LOAD).where(PTMRecord.id == row.id))
    ).scalar_one()
    return _serialize(row)


@router.delete("/{ptm_id}", response_model=MessageResponse)
async def delete_ptm_record(
    ptm_id: UUID,
    _: object = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(select(PTMRecord).where(PTMRecord.id == ptm_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="PTM record not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="PTM record deleted")
