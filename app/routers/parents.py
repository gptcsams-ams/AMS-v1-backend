from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin, require_roles
from app.core.security import hash_password
from app.models.parent import Parent
from app.models.student import Student
from app.models.student_parent import StudentParent
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.parent import (
    ChildrenResponse,
    ParentCreate,
    ParentRegister,
    ParentResponse,
    ParentStudentLinkCreate,
    ParentUpdate,
)
from app.services.parent_service import ParentService

router = APIRouter()

require_parent = require_roles("PARENT")


# ── Parent Portal self-reference (declared before /{parent_id} so "me" is not
#    parsed as a UUID) ─────────────────────────────────────────────────────────

@router.get("/me/children", response_model=ChildrenResponse)
async def my_children(
    year_id: UUID | None = Query(default=None),
    current_user: object = Depends(require_parent),
    db: AsyncSession = Depends(get_db),
):
    """Return the logged-in parent's children with enrollment context and
    computed aggregates (today_status, attendance_pct, pending_leaves).

    The active branch filter used by Admin/Teacher roles does NOT apply here:
    a parent sees all linked children regardless of branch.
    """
    svc = ParentService(db)
    children = await svc.get_children_with_context(current_user.id, year_id)
    return ChildrenResponse(data=children)


@router.get("", response_model=list[ParentResponse])
async def list_parents(search: str | None = Query(default=None), _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    stmt = select(Parent)
    if search:
        stmt = stmt.where(or_(Parent.full_name.ilike(f"%{search}%"), Parent.contact_number.ilike(f"%{search}%")))
    parents = list((await db.execute(stmt)).scalars().all())

    # Count linked students per parent (CHILDREN column).
    counts = dict((await db.execute(
        select(StudentParent.parent_id, func.count(StudentParent.student_id))
        .group_by(StudentParent.parent_id)
    )).all())

    return [
        ParentResponse(
            id=p.id,
            user_id=p.user_id,
            full_name=p.full_name,
            contact_number=p.contact_number,
            email=p.email,
            address=p.address,
            occupation=p.occupation,
            created_at=p.created_at,
            children_count=counts.get(p.id, 0),
        )
        for p in parents
    ]


@router.get("/{parent_id}", response_model=ParentResponse)
async def get_parent(parent_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Parent).where(Parent.id == parent_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Parent not found")
    return row


@router.get("/{parent_id}/children")
async def get_children(parent_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(StudentParent).where(StudentParent.parent_id == parent_id))
    return list(rows.scalars().all())


@router.post("", response_model=ParentResponse)
async def create_parent(
    payload: ParentRegister,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Register a parent: creates the login User, the Parent profile, and links
    one or more students by admission number. Email must be globally unique.
    """
    # 1. Email must be unique across all users (login credential).
    clash = (await db.execute(
        select(User).where(User.email == payload.email)
    )).scalar_one_or_none()
    if clash:
        raise HTTPException(
            status_code=409,
            detail=f"The email '{payload.email}' is already registered. Use a unique email address.",
        )

    # 2. Resolve every admission number to a student; reject unknown ones.
    students = (await db.execute(
        select(Student).where(Student.admission_number.in_(payload.admission_numbers))
    )).scalars().all()
    found = {s.admission_number for s in students}
    missing = [a for a in payload.admission_numbers if a not in found]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"No student found for admission number(s): {', '.join(missing)}",
        )

    # 3. Create the login User (role=PARENT).
    user = User(
        name=payload.username,
        email=payload.email,
        password=hash_password(payload.password),
        role="PARENT",
        branch_id=getattr(current_user, "branch_id", None),
    )
    db.add(user)
    await db.flush()  # assign user.id

    # 4. Create the Parent profile (username is the portal display name).
    parent = Parent(
        user_id=user.id,
        full_name=payload.username,
        contact_number=payload.contact_number,
        email=payload.email,
        occupation=payload.occupation,
        address=payload.address,
    )
    db.add(parent)
    await db.flush()  # assign parent.id

    # 5. Link each student. The first one is marked primary.
    for index, student in enumerate(students):
        db.add(StudentParent(
            student_id=student.id,
            parent_id=parent.id,
            relationship_type=payload.relationship_type,
            is_primary=(index == 0),
        ))

    await db.commit()
    await db.refresh(parent)
    return parent


@router.patch("/{parent_id}", response_model=ParentResponse)
async def update_parent(parent_id: UUID, payload: ParentUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Parent).where(Parent.id == parent_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Parent not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{parent_id}", response_model=MessageResponse)
async def delete_parent(parent_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Parent).where(Parent.id == parent_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Parent not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Parent deleted")


@router.post("/{parent_id}/link-student", response_model=MessageResponse)
async def link_student(parent_id: UUID, payload: ParentStudentLinkCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = StudentParent(parent_id=parent_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    return MessageResponse(message="Student linked")


@router.delete("/{parent_id}/students/{student_id}", response_model=MessageResponse)
async def unlink_student(parent_id: UUID, student_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(StudentParent).where(StudentParent.parent_id == parent_id, StudentParent.student_id == student_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Student unlinked")
