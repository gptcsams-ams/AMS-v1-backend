import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete as sa_delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.core.dependencies import require_admin, require_roles
from app.core.security import hash_password
from app.models.parent import Parent
from app.models.student import Student
from app.models.student_parent import StudentParent
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.parent import (
    ChildrenResponse,
    CreatedParentInfo,
    ParentCreate,
    ParentEntry,
    ParentFamilyRegister,
    ParentFamilyResponse,
    ParentRegister,
    ParentResponse,
    ParentStudentLinkCreate,
    ParentUpdate,
)
from app.services.parent_service import ParentService

router = APIRouter()

require_parent = require_roles("PARENT")


def _generate_parent_password(name: str, contact_number: str) -> str:
    """Default password: parent's first name + last 4 digits of their phone,
    plain with no spaces or symbols (e.g. 'Rajesh' + '9876543210' -> 'Rajesh3210').
    """
    first = (name or "").strip().split(" ")[0] if name and name.strip() else "parent"
    digits = "".join(ch for ch in (contact_number or "") if ch.isdigit())
    last4 = digits[-4:]
    return f"{first}{last4}"


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


@router.post("/family", response_model=ParentFamilyResponse)
async def create_parent_family(
    payload: ParentFamilyRegister,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Register a Father and/or a Mother in one go, each as its own login
    account, both linked to the selected student(s).

    Passwords are auto-generated (first name + last 4 digits of phone) and
    returned once so the admin can pass them to the parents.
    """
    entries: list[tuple[str, ParentEntry]] = []
    if payload.father:
        entries.append(("FATHER", payload.father))
    if payload.mother:
        entries.append(("MOTHER", payload.mother))
    if not entries:
        raise HTTPException(
            status_code=422,
            detail="Provide at least a Father or a Mother.",
        )

    # Emails must be unique among the submitted entries.
    emails = [e.email for _, e in entries]
    if len(emails) != len(set(emails)):
        raise HTTPException(
            status_code=409,
            detail="Father and Mother must use different email addresses.",
        )

    # Contact numbers must be unique among the submitted entries.
    numbers = [e.contact_number for _, e in entries]
    if len(numbers) != len(set(numbers)):
        raise HTTPException(
            status_code=409,
            detail="Father and Mother must use different contact numbers.",
        )

    # Each email must be globally unique across existing users.
    for _, entry in entries:
        clash = (await db.execute(
            select(User).where(User.email == entry.email)
        )).scalar_one_or_none()
        if clash:
            raise HTTPException(
                status_code=409,
                detail=f"The email '{entry.email}' is already registered. Use a unique email address.",
            )

    # Each contact number must be unique across existing parents (DB constraint).
    for _, entry in entries:
        clash = (await db.execute(
            select(Parent).where(Parent.contact_number == entry.contact_number)
        )).scalar_one_or_none()
        if clash:
            raise HTTPException(
                status_code=409,
                detail=f"The contact number '{entry.contact_number}' is already registered to another parent.",
            )

    # Resolve every admission number to a student; reject unknown ones.
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

    created: list[CreatedParentInfo] = []

    for index, (relationship, entry) in enumerate(entries):
        plain_password = _generate_parent_password(entry.name, entry.contact_number)

        user = User(
            name=entry.name,
            email=entry.email,
            password=hash_password(plain_password),
            role="PARENT",
            branch_id=getattr(current_user, "branch_id", None),
        )
        db.add(user)
        await db.flush()  # assign user.id

        parent = Parent(
            user_id=user.id,
            full_name=entry.name,
            contact_number=entry.contact_number,
            email=entry.email,
            occupation=entry.occupation,
            address=payload.address,
        )
        db.add(parent)
        await db.flush()  # assign parent.id

        # Link each student. The first parent (Father if present) is primary.
        for student in students:
            db.add(StudentParent(
                student_id=student.id,
                parent_id=parent.id,
                relationship_type=relationship,
                is_primary=(index == 0),
            ))

        created.append(CreatedParentInfo(
            id=parent.id,
            full_name=parent.full_name,
            email=parent.email,
            relationship_type=relationship,
            password=plain_password,
        ))

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A parent with this email or contact number already exists.",
        )

    # ── Fire "Your account has been created" emails — NON-BLOCKING ────────────
    # Uses the branch's SMTP settings; silently skips if email isn't configured.
    # The plaintext password is only available here (it is hashed in storage).
    recipients = [
        {
            "parent_id": str(c.id),
            "email": c.email,
            "name": c.full_name,
            "password": c.password,
            "relationship": c.relationship_type,
        }
        for c in created
    ]
    # Key the email off the student's branch (always set), falling back to the
    # admin's branch — email settings are configured per branch.
    email_branch_id = students[0].branch_id if students else getattr(current_user, "branch_id", None)
    from app.services.email_service import send_account_created_emails
    asyncio.create_task(
        send_account_created_emails(
            branch_id=str(email_branch_id) if email_branch_id else "",
            recipients=recipients,
            db=AsyncSessionLocal(),
        )
    )

    return ParentFamilyResponse(parents=created)


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

    # Delete at the SQL level so we rely on DB foreign-key cascades
    # (student_parents -> ON DELETE CASCADE) instead of ORM relationship
    # handling, which would try to load unrelated tables.
    user_id = row.user_id
    if user_id:
        # Removing the login User cascades to the Parent row and its links.
        await db.execute(sa_delete(User).where(User.id == user_id))
    else:
        await db.execute(sa_delete(Parent).where(Parent.id == parent_id))
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
