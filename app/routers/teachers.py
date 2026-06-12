from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.core.security import hash_password
from app.models.academic_class import AcademicClass
from app.models.subject import Subject
from app.models.teacher_profile import TeacherProfile
from app.models.teacher_subject_eligibility import TeacherSubjectEligibility
from app.models.timetable_entry import TimetableEntry
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.teacher import TeacherCreate, TeacherEligibilityCreate, TeacherResponse, TeacherUpdate
from app.services.imagekit_service import upload_imagekit_file

router = APIRouter()


def _teacher_response(row: TeacherProfile) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "branch_id": row.branch_id,
        "employee_id": row.employee_id,
        "department": row.department,
        "designation": row.designation,
        "profile_image_url": row.profile_image_url,
        "contact_number": row.contact_number,
        "name": row.user.name if row.user else None,
        "email": row.user.email if row.user else None,
        "created_at": row.created_at,
        "eligibilities": [
            {
                "id": elig.id,
                "subject_id": elig.subject_id,
                "class_id": elig.class_id,
                "subject_name": elig.subject.name if elig.subject else None,
                "grade": getattr(getattr(elig, "academic_class", None), "grade", None),
            }
            for elig in row.subject_eligibilities
        ],
    }


def _teacher_options():
    return (
        selectinload(TeacherProfile.user),
        selectinload(TeacherProfile.subject_eligibilities).selectinload(TeacherSubjectEligibility.subject),
        selectinload(TeacherProfile.subject_eligibilities).selectinload(TeacherSubjectEligibility.academic_class),
    )


@router.get("", response_model=list[TeacherResponse])
async def list_teachers(_: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(TeacherProfile).options(*_teacher_options()))
    return [_teacher_response(row) for row in rows.scalars().all()]


@router.get("/{teacher_id}", response_model=TeacherResponse)
async def get_teacher(teacher_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(TeacherProfile)
        .options(*_teacher_options())
        .where(TeacherProfile.id == teacher_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return _teacher_response(row)


@router.get("/{teacher_id}/timetable")
async def get_teacher_timetable(teacher_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(TimetableEntry).where(TimetableEntry.teacher_profile_id == teacher_id))
    return list(rows.scalars().all())


@router.get("/{teacher_id}/eligibilities")
async def get_teacher_eligibilities(teacher_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(TeacherSubjectEligibility)
        .options(selectinload(TeacherSubjectEligibility.subject))
        .options(selectinload(TeacherSubjectEligibility.academic_class))
        .where(TeacherSubjectEligibility.teacher_profile_id == teacher_id)
    )
    return [
        {
            "id": row.id,
            "subject_id": row.subject_id,
            "class_id": row.class_id,
            "subject_name": row.subject.name if row.subject else None,
            "grade": row.academic_class.grade if row.academic_class else None,
        }
        for row in rows.scalars().all()
    ]


@router.post("", response_model=TeacherResponse)
async def create_teacher(payload: TeacherCreate, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    data = payload.model_dump(exclude={"subject_ids"})
    branch_id = data.get("branch_id") or current_user.branch_id
    if not branch_id:
        raise HTTPException(status_code=400, detail="Select a branch before adding teachers")

    user_id = data.pop("user_id", None)
    if user_id:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="Teacher user not found")
    else:
        if not payload.name or not payload.email or not payload.password:
            raise HTTPException(status_code=400, detail="Teacher name, email and password are required")
        existing = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="A user with this email already exists. Use a unique teacher email.")
        user = User(
            name=payload.name.strip(),
            email=payload.email,
            password=hash_password(payload.password),
            role="TEACHER",
            branch_id=branch_id,
            is_active=True,
        )
        db.add(user)
        await db.flush()

    row = TeacherProfile(
        user_id=user.id,
        branch_id=branch_id,
        employee_id=payload.employee_id,
        department=data.get("department"),
        designation=data.get("designation"),
        contact_number=data.get("contact_number"),
        profile_image_url=data.get("profile_image_url"),
    )
    db.add(row)
    await db.flush()

    if payload.subject_ids:
        subject_rows = list((await db.execute(select(Subject).where(Subject.id.in_(payload.subject_ids)))).scalars().all())
        row.department = ", ".join(subject.name for subject in subject_rows)
        classes = list((await db.execute(select(AcademicClass).where(AcademicClass.branch_id == branch_id))).scalars().all())
        if classes:
            for subject in subject_rows:
                for academic_class in classes:
                    db.add(TeacherSubjectEligibility(
                        teacher_profile_id=row.id,
                        subject_id=subject.id,
                        class_id=academic_class.id,
                    ))

    await db.commit()
    saved = (await db.execute(
        select(TeacherProfile)
        .options(*_teacher_options())
        .where(TeacherProfile.id == row.id)
    )).scalar_one()
    return _teacher_response(saved)


@router.post("/profile-photo")
async def upload_teacher_profile_photo(
    photo: UploadFile = File(...),
    _: object = Depends(require_admin),
):
    image_url = await upload_imagekit_file(photo, "/ams/teachers/profile")
    return {"image_url": image_url}


@router.post("/{teacher_id}/eligibilities")
async def add_eligibility(teacher_id: UUID, payload: TeacherEligibilityCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if not payload.class_id:
        raise HTTPException(status_code=400, detail="Grade level is required")
    row = TeacherSubjectEligibility(teacher_profile_id=teacher_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    return {"id": str(row.id)}


@router.delete("/{teacher_id}/eligibilities/{elig_id}", response_model=MessageResponse)
async def delete_eligibility(teacher_id: UUID, elig_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(TeacherSubjectEligibility).where(TeacherSubjectEligibility.id == elig_id, TeacherSubjectEligibility.teacher_profile_id == teacher_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Eligibility not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Eligibility deleted")


@router.patch("/{teacher_id}", response_model=TeacherResponse)
async def update_teacher(teacher_id: UUID, payload: TeacherUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(TeacherProfile).where(TeacherProfile.id == teacher_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Teacher not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    saved = (await db.execute(
        select(TeacherProfile)
        .options(*_teacher_options())
        .where(TeacherProfile.id == teacher_id)
    )).scalar_one()
    return _teacher_response(saved)


@router.delete("/{teacher_id}", response_model=MessageResponse)
async def delete_teacher(teacher_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(TeacherProfile).where(TeacherProfile.id == teacher_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Teacher not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Teacher deleted")
