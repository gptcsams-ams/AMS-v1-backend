"""ParentService — Parent Portal business logic.

Implements the AMS Parent Portal spec (v1.0): a parent logs in with one
credential and tracks every linked child. The key method is
``get_children_with_context`` which returns each child with lightweight,
service-computed aggregates: today's attendance status, the running
attendance percentage for the academic year, and the count of pending
leave requests.

Design notes (Redis-free):
  - The spec describes a ``parent_children:{parent_id}:{year_id}`` Redis cache
    with a 15-minute TTL. Redis has been removed from this project, so the
    aggregates are computed directly from the database on each call. The
    queries are small (per-child COUNT/aggregate) and indexed.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic_class import AcademicClass
from app.models.academic_year import AcademicYear
from app.models.attendance import Attendance
from app.models.leave_request import LeaveRequest
from app.models.parent import Parent
from app.models.section import Section
from app.models.student import Student
from app.models.student_enrollment import StudentEnrollment
from app.models.student_parent import StudentParent
from app.schemas.parent import ChildEnrollment, ChildSummary

# Attendance statuses that count as "attended" for the running percentage.
_PRESENT_STATUSES = ("PRESENT", "LATE")


class ParentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Public API ──────────────────────────────────────────────────────────────

    async def get_children_with_context(
        self, user_id: UUID, year_id: UUID | None = None
    ) -> list[ChildSummary]:
        """Return all children linked to ``user_id`` with enrollment context
        and computed aggregates, ordered primary-first then alphabetically.

        ``year_id`` defaults to the current academic year when omitted.
        """
        parent = await self._resolve_parent(user_id)

        if year_id is None:
            year_id = await self._current_year_id()

        # All StudentParent links for this parent.
        links = (await self.db.execute(
            select(StudentParent).where(StudentParent.parent_id == parent.id)
        )).scalars().all()
        if not links:
            return []

        student_ids = [link.student_id for link in links]
        link_by_student = {link.student_id: link for link in links}

        students = (await self.db.execute(
            select(Student).where(Student.id.in_(student_ids))
        )).scalars().all()
        student_by_id = {s.id: s for s in students}

        today = date.today()
        summaries: list[ChildSummary] = []
        for sid in student_ids:
            student = student_by_id.get(sid)
            if not student:
                continue
            link = link_by_student[sid]

            enrollment = await self._active_enrollment(sid, year_id)
            today_status = await self._today_status(sid, year_id, today)
            attendance_pct = await self._attendance_pct(sid, year_id)
            pending_leaves = await self._pending_leave_count(sid, year_id)

            summaries.append(ChildSummary(
                student_id        = student.id,
                first_name        = student.first_name,
                last_name         = student.last_name,
                admission_number  = student.admission_number,
                student_photo_url = student.student_photo_url,
                relationship_type = link.relationship_type,
                is_primary        = link.is_primary,
                enrollment        = enrollment,
                today_status      = today_status,
                attendance_pct    = attendance_pct,
                pending_leaves    = pending_leaves,
            ))

        # Order: primary contact's children first, then alphabetical by first name.
        summaries.sort(key=lambda c: (not c.is_primary, c.first_name.lower()))
        return summaries

    # ── Private helpers ─────────────────────────────────────────────────────────

    async def _resolve_parent(self, user_id: UUID) -> Parent:
        parent = (await self.db.execute(
            select(Parent).where(Parent.user_id == user_id)
        )).scalar_one_or_none()
        if not parent:
            raise HTTPException(
                status_code=404,
                detail="No parent profile is linked to this account. Please contact the school office.",
            )
        return parent

    async def _current_year_id(self) -> UUID | None:
        return (await self.db.execute(
            select(AcademicYear.id).where(AcademicYear.is_current == True)  # noqa: E712
        )).scalar_one_or_none()

    async def _active_enrollment(
        self, student_id: UUID, year_id: UUID | None
    ) -> ChildEnrollment | None:
        if year_id is None:
            return None
        row = (await self.db.execute(
            select(
                StudentEnrollment.section_id,
                StudentEnrollment.roll_number,
                StudentEnrollment.status,
                Section.name.label("section_name"),
                AcademicClass.grade,
            )
            .join(Section, Section.id == StudentEnrollment.section_id)
            .join(AcademicClass, AcademicClass.id == Section.class_id)
            .where(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.academic_year_id == year_id,
                StudentEnrollment.status == "ACTIVE",
            )
        )).first()
        if not row:
            return None
        # Compose a human-friendly section label, e.g. "Class 9 - B".
        section_label = f"{row.grade} - {row.section_name}" if row.grade else row.section_name
        return ChildEnrollment(
            section_id   = row.section_id,
            section_name = section_label,
            year_id      = year_id,
            roll_number  = row.roll_number,
            status       = row.status,
        )

    async def _today_status(
        self, student_id: UUID, year_id: UUID | None, today: date
    ) -> str | None:
        """Today's attendance status, or None if no window has produced a record yet."""
        q = select(Attendance.status).where(
            Attendance.student_id == student_id,
            Attendance.attendance_date == today,
        )
        if year_id is not None:
            q = q.where(Attendance.academic_year_id == year_id)
        # If multiple windows exist, prefer the "most attended" status.
        rows = (await self.db.execute(q)).scalars().all()
        if not rows:
            return None
        if any(s == "PRESENT" for s in rows):
            return "PRESENT"
        if any(s == "LATE" for s in rows):
            return "LATE"
        if any(s == "EXCUSED" for s in rows):
            return "EXCUSED"
        return rows[0]

    async def _attendance_pct(self, student_id: UUID, year_id: UUID | None) -> float:
        """Running attendance % for the year: (present + late) / total * 100."""
        q = select(
            func.count().label("total"),
            func.count().filter(Attendance.status.in_(_PRESENT_STATUSES)).label("present"),
        ).where(Attendance.student_id == student_id)
        if year_id is not None:
            q = q.where(Attendance.academic_year_id == year_id)
        row = (await self.db.execute(q)).first()
        total = row.total or 0
        present = row.present or 0
        if not total:
            return 0.0
        return round(present / total * 100, 1)

    async def _pending_leave_count(self, student_id: UUID, year_id: UUID | None) -> int:
        q = select(func.count()).where(
            LeaveRequest.student_id == student_id,
            LeaveRequest.status == "PENDING",
        )
        if year_id is not None:
            q = q.where(LeaveRequest.academic_year_id == year_id)
        return (await self.db.execute(q)).scalar_one() or 0
