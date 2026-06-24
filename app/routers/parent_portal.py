"""
Parent Portal API — /api/v1/parent-portal
All routes require role: PARENT
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_roles
from app.models.parent import Parent
from app.models.student_parent import StudentParent
from app.models.student import Student
from app.models.student_enrollment import StudentEnrollment
from app.models.attendance import Attendance
from app.models.leave_request import LeaveRequest
from app.models.school_calendar import SchoolCalendar
from app.models.notification import Notification
from app.models.section import Section
from app.schemas.leave import LeaveCreate

router = APIRouter()
require_parent = require_roles("PARENT")


# ── helpers ────────────────────────────────────────────────────────────────────

async def _get_parent(db: AsyncSession, user_id: UUID) -> Parent:
    row = (await db.execute(select(Parent).where(Parent.user_id == user_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Parent profile not found. Please contact admin.")
    return row


async def _get_linked_student_ids(db: AsyncSession, parent_id: UUID) -> list[UUID]:
    rows = (await db.execute(
        select(StudentParent.student_id).where(StudentParent.parent_id == parent_id)
    )).scalars().all()
    return list(rows)


async def _assert_owns_student(student_id: UUID, owned_ids: list[UUID]):
    if student_id not in owned_ids:
        raise HTTPException(status_code=403, detail="Access denied to this student")


# ── 1. My children ─────────────────────────────────────────────────────────────

@router.get("/children")
async def my_children(
    user=Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    """Return all children linked to the logged-in parent."""
    parent = await _get_parent(db, user.id)
    student_ids = await _get_linked_student_ids(db, parent.id)
    if not student_ids:
        return []
    rows = (await db.execute(
        select(Student).where(Student.id.in_(student_ids))
    )).scalars().all()
    return [
        {
            "id": str(s.id),
            "name": f"{s.first_name} {s.last_name}",
            "admission_number": s.admission_number,
            "gender": s.gender,
        }
        for s in rows
    ]


# ── 2. Attendance ──────────────────────────────────────────────────────────────

@router.get("/attendance/{student_id}")
async def student_attendance(
    student_id: UUID,
    from_date: str | None = None,
    to_date: str | None = None,
    user=Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    parent = await _get_parent(db, user.id)
    owned = await _get_linked_student_ids(db, parent.id)
    await _assert_owns_student(student_id, owned)

    stmt = select(Attendance).where(Attendance.student_id == student_id).order_by(Attendance.attendance_date.desc())
    if from_date:
        stmt = stmt.where(Attendance.attendance_date >= from_date)
    if to_date:
        stmt = stmt.where(Attendance.attendance_date <= to_date)

    rows = (await db.execute(stmt)).scalars().all()
    total = len(rows)
    present = sum(1 for r in rows if r.status == "PRESENT")
    absent = sum(1 for r in rows if r.status == "ABSENT")
    late = sum(1 for r in rows if r.status == "LATE")

    return {
        "summary": {
            "total": total,
            "present": present,
            "absent": absent,
            "late": late,
            "percentage": round(present / total * 100, 1) if total else 0,
        },
        "records": [
            {
                "id": str(r.id),
                "date": str(r.attendance_date),
                "status": r.status,
                "marked_by": r.marked_by,
                "is_overridden": r.is_overridden,
                "first_detected_at": r.first_detected_at.isoformat() if r.first_detected_at else None,
            }
            for r in rows
        ],
    }


# ── 3. Calendar (read-only) ────────────────────────────────────────────────────

@router.get("/calendar")
async def school_calendar(
    branch_id: str | None = None,
    year: int | None = None,
    month: int | None = None,
    user=Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SchoolCalendar).order_by(SchoolCalendar.date)
    if branch_id:
        stmt = stmt.where(SchoolCalendar.branch_id == branch_id)
    if year:
        stmt = stmt.where(func.extract("year", SchoolCalendar.date) == year)
    if month:
        stmt = stmt.where(func.extract("month", SchoolCalendar.date) == month)

    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "date": str(r.date),
            "day_type": r.day_type,
            "reason": r.reason,
        }
        for r in rows
    ]


# ── 4. Leaves ──────────────────────────────────────────────────────────────────

@router.get("/leaves/{student_id}")
async def my_leaves(
    student_id: UUID,
    status: str | None = None,
    user=Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    parent = await _get_parent(db, user.id)
    owned = await _get_linked_student_ids(db, parent.id)
    await _assert_owns_student(student_id, owned)

    stmt = (
        select(LeaveRequest)
        .where(LeaveRequest.student_id == student_id)
        .order_by(LeaveRequest.created_at.desc())
    )
    if status:
        stmt = stmt.where(LeaveRequest.status == status.upper())

    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "from_date": str(r.from_date),
            "to_date": str(r.to_date),
            "reason": r.reason,
            "leave_type": r.leave_type,
            "status": r.status,
            "review_remarks": r.review_remarks,
            "version": r.version,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/leaves")
async def apply_leave(
    payload: LeaveCreate,
    user=Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    parent = await _get_parent(db, user.id)
    owned = await _get_linked_student_ids(db, parent.id)
    await _assert_owns_student(payload.student_id, owned)

    row = LeaveRequest(**payload.model_dump(), requested_by=user.id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": str(row.id), "status": row.status, "message": "Leave applied successfully"}


@router.patch("/leaves/{leave_id}")
async def edit_leave(
    leave_id: UUID,
    from_date: str | None = None,
    to_date: str | None = None,
    reason: str | None = None,
    leave_type: str | None = None,
    user=Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    """Parent can only edit their own PENDING leaves."""
    parent = await _get_parent(db, user.id)
    owned = await _get_linked_student_ids(db, parent.id)

    row = (await db.execute(select(LeaveRequest).where(LeaveRequest.id == leave_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Leave not found")
    await _assert_owns_student(row.student_id, owned)
    if row.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Cannot edit a leave with status '{row.status}'. Only PENDING leaves can be edited.")

    updates: dict = {}
    if from_date:
        updates["from_date"] = from_date
    if to_date:
        updates["to_date"] = to_date
    if reason:
        updates["reason"] = reason
    if leave_type:
        updates["leave_type"] = leave_type

    if updates:
        await db.execute(update(LeaveRequest).where(LeaveRequest.id == leave_id).values(**updates))
        await db.commit()
        await db.refresh(row)

    return {
        "id": str(row.id),
        "from_date": str(row.from_date),
        "to_date": str(row.to_date),
        "reason": row.reason,
        "leave_type": row.leave_type,
        "status": row.status,
    }


@router.delete("/leaves/{leave_id}")
async def cancel_leave(
    leave_id: UUID,
    user=Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    parent = await _get_parent(db, user.id)
    owned = await _get_linked_student_ids(db, parent.id)

    row = (await db.execute(select(LeaveRequest).where(LeaveRequest.id == leave_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Leave not found")
    await _assert_owns_student(row.student_id, owned)
    if row.status not in ("PENDING",):
        raise HTTPException(status_code=400, detail="Only PENDING leaves can be cancelled")

    await db.execute(
        update(LeaveRequest).where(LeaveRequest.id == leave_id).values(status="CANCELLED")
    )
    await db.commit()
    return {"message": "Leave cancelled"}


# ── 5. Notifications ───────────────────────────────────────────────────────────

@router.get("/notifications")
async def my_notifications(
    student_id: UUID | None = None,
    unread_only: bool = False,
    limit: int = 50,
    user=Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    """Notification log scoped to the logged-in parent. Optionally filter to one
    child via ?student_id= (spec §6.6). The message preview is read from the
    JSONB payload body since the new Notification schema has no `message` column.
    """
    parent = await _get_parent(db, user.id)
    owned = await _get_linked_student_ids(db, parent.id)

    stmt = (
        select(Notification)
        .where(Notification.parent_id == parent.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if student_id:
        await _assert_owns_student(student_id, owned)
        stmt = stmt.where(Notification.student_id == student_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))

    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "message": (r.payload or {}).get("body", ""),
            "channel": r.channel,
            "trigger_type": r.trigger_type,
            "status": r.status,
            "student_id": str(r.student_id) if r.student_id else None,
            "is_read": r.read_at is not None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.patch("/notifications/{notif_id}/read")
async def mark_notification_read(
    notif_id: UUID,
    user=Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    parent = await _get_parent(db, user.id)
    await db.execute(
        update(Notification)
        .where(Notification.id == notif_id, Notification.parent_id == parent.id)
        .values(read_at=datetime.utcnow(), status="READ")
    )
    await db.commit()
    return {"message": "Marked as read"}


@router.patch("/notifications/read-all")
async def mark_all_read(
    user=Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    parent = await _get_parent(db, user.id)
    await db.execute(
        update(Notification)
        .where(Notification.parent_id == parent.id, Notification.read_at.is_(None))
        .values(read_at=datetime.utcnow(), status="READ")
    )
    await db.commit()
    return {"message": "All notifications marked as read"}


@router.get("/notifications/unread-count")
async def unread_count(
    user=Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    parent = await _get_parent(db, user.id)
    count = (await db.execute(
        select(func.count()).where(
            Notification.parent_id == parent.id,
            Notification.read_at.is_(None),
        )
    )).scalar() or 0
    return {"count": count}


# ── 6. Notes (read-only for parent) ───────────────────────────────────────────

@router.get("/notes/{student_id}")
async def student_notes(
    student_id: UUID,
    user=Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    from app.models.note import Note
    parent = await _get_parent(db, user.id)
    owned = await _get_linked_student_ids(db, parent.id)
    await _assert_owns_student(student_id, owned)

    # get student's section
    enroll = (await db.execute(
        select(StudentEnrollment.section_id).where(StudentEnrollment.student_id == student_id)
    )).scalar_one_or_none()
    if not enroll:
        return []

    rows = (await db.execute(
        select(Note).where(Note.section_id == enroll).order_by(Note.created_at.desc())
    )).scalars().all()
    return [{"id": str(r.id), "title": r.title, "content": r.content, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


# ── 7. Assignments (read-only for parent) ─────────────────────────────────────

@router.get("/assignments/{student_id}")
async def student_assignments(
    student_id: UUID,
    user=Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    from app.models.assignment import Assignment
    parent = await _get_parent(db, user.id)
    owned = await _get_linked_student_ids(db, parent.id)
    await _assert_owns_student(student_id, owned)

    enroll = (await db.execute(
        select(StudentEnrollment.section_id).where(StudentEnrollment.student_id == student_id)
    )).scalar_one_or_none()
    if not enroll:
        return []

    rows = (await db.execute(
        select(Assignment).where(Assignment.section_id == enroll).order_by(Assignment.due_date.asc())
    )).scalars().all()
    return [{"id": str(r.id), "title": r.title, "description": r.description, "due_date": str(r.due_date), "total_marks": r.total_marks} for r in rows]


# ── 8. Test Marks (read-only for parent) ──────────────────────────────────────

@router.get("/marks/{student_id}")
async def student_marks(
    student_id: UUID,
    user=Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    from app.models.test_mark import TestMark
    parent = await _get_parent(db, user.id)
    owned = await _get_linked_student_ids(db, parent.id)
    await _assert_owns_student(student_id, owned)

    rows = (await db.execute(
        select(TestMark).where(TestMark.student_id == student_id).order_by(TestMark.created_at.desc())
    )).scalars().all()
    return [
        {
            "id": str(r.id),
            "test_name": r.test_name,
            "marks_obtained": r.marks_obtained,
            "total_marks": r.total_marks,
            "percentage": round(r.marks_obtained / r.total_marks * 100, 1) if r.total_marks else 0,
            "test_date": str(r.test_date) if r.test_date else None,
        }
        for r in rows
    ]
