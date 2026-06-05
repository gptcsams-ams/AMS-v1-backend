from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models.branch import Branch
from app.models.attendance import Attendance
from app.models.leave_request import LeaveRequest
from app.models.student import Student
from app.models.student_face import StudentFace
from app.models.student_enrollment import StudentEnrollment
from app.schemas.common import MessageResponse
from app.schemas.student import StudentCreate, StudentFaceResponse, StudentResponse, StudentUpdate
from app.services.embedding_cache_service import invalidate_section_cache
from app.services.face_embedding_service import analyze_face_upload
from app.services.imagekit_service import upload_imagekit_file
from app.services.student_service import import_students_csv

router = APIRouter()


async def _with_face_summary(db: AsyncSession, students: list[Student]) -> list[dict]:
    student_ids = [student.id for student in students]
    if not student_ids:
        return []

    face_rows = await db.execute(
        select(StudentFace.student_id, StudentFace.image_url)
        .where(StudentFace.student_id.in_(student_ids), StudentFace.is_active == True)
        .order_by(StudentFace.created_at.desc())
    )
    face_counts: dict[UUID, int] = {}
    face_images: dict[UUID, str] = {}
    for student_id, image_url in face_rows.all():
        face_counts[student_id] = face_counts.get(student_id, 0) + 1
        face_images.setdefault(student_id, image_url)

    return [
        {
            **StudentResponse.model_validate(student).model_dump(),
            "face_count": face_counts.get(student.id, 0),
            "face_image_url": face_images.get(student.id),
        }
        for student in students
    ]


@router.get("", response_model=list[StudentResponse])
async def list_students(
    section_id: UUID | None = Query(default=None),
    year_id: UUID | None = Query(default=None),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Student)
    if section_id or year_id:
        stmt = stmt.join(StudentEnrollment, StudentEnrollment.student_id == Student.id)
    if section_id:
        stmt = stmt.where(StudentEnrollment.section_id == section_id)
    if year_id:
        stmt = stmt.where(StudentEnrollment.academic_year_id == year_id)

    rows = await db.execute(stmt.where(Student.is_active == True).order_by(Student.created_at.desc()))
    return await _with_face_summary(db, list(rows.scalars().all()))


@router.get("/{student_id}", response_model=StudentResponse)
async def get_student(student_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Student not found")
    return (await _with_face_summary(db, [row]))[0]


@router.get("/{student_id}/attendance")
async def get_student_attendance(student_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Attendance).where(Attendance.student_id == student_id))
    return list(rows.scalars().all())


@router.get("/{student_id}/faces", response_model=list[StudentFaceResponse])
async def get_student_faces(student_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(StudentFace)
        .where(StudentFace.student_id == student_id, StudentFace.is_active == True)
        .order_by(StudentFace.created_at.desc())
    )
    return list(rows.scalars().all())


@router.get("/{student_id}/leaves")
async def get_student_leaves(student_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(LeaveRequest).where(LeaveRequest.student_id == student_id))
    return list(rows.scalars().all())


@router.post("", response_model=StudentResponse)
async def create_student(
    payload: StudentCreate,
    current_user: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(
        select(Student).where(Student.admission_number == payload.admission_number)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Admission number '{payload.admission_number}' already exists. Use a unique admission number.",
        )

    data = payload.model_dump()
    branch = (await db.execute(select(Branch).where(Branch.id == payload.branch_id))).scalar_one_or_none()
    if not branch:
        fallback_branch_id = getattr(current_user, "branch_id", None)
        if fallback_branch_id:
            branch = (await db.execute(select(Branch).where(Branch.id == fallback_branch_id))).scalar_one_or_none()
        if not branch:
            branch = (await db.execute(select(Branch).limit(1))).scalar_one_or_none()
        if not branch:
            raise HTTPException(status_code=400, detail="No branch is configured. Create a branch before adding students.")
        data["branch_id"] = branch.id

    row = Student(**data)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.post("/bulk-import")
async def bulk_import_students(file: UploadFile = File(...), _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    data = await file.read()
    count = await import_students_csv(db, data.decode("utf-8"))
    return {"imported": count}


@router.post("/{student_id}/faces")
async def add_student_face(student_id: UUID, image: UploadFile = File(...), _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    student = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    analysis = await analyze_face_upload(image)
    image_url = await upload_imagekit_file(image, f"/ams/students/{student_id}/faces")
    face = StudentFace(
        student_id=student_id,
        image_url=image_url,
        embedding=analysis.embedding,
        quality_score=analysis.quality_score,
        blur_score=analysis.blur_score,
        brightness_score=analysis.brightness_score,
        face_bbox=analysis.face_bbox,
        source="MANUAL_UPLOAD",
    )
    db.add(face)
    await db.commit()
    await db.refresh(face)
    await invalidate_section_cache(db, student_id)
    return {
        "message": "Face uploaded",
        "face_id": str(face.id),
        "image_url": face.image_url,
        "quality_score": face.quality_score,
        "blur_score": face.blur_score,
        "brightness_score": face.brightness_score,
        "face_bbox": face.face_bbox,
    }


@router.post("/{student_id}/photo", response_model=StudentResponse)
async def upload_student_photo(
    student_id: UUID,
    photo: UploadFile = File(...),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    student = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    student.student_photo_url = await upload_imagekit_file(photo, f"/ams/students/{student_id}/profile")
    await db.commit()
    await db.refresh(student)
    return student


@router.patch("/{student_id}", response_model=StudentResponse)
async def update_student(student_id: UUID, payload: StudentUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Student not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{student_id}/faces/{face_id}", response_model=MessageResponse)
async def delete_face(student_id: UUID, face_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(StudentFace).where(StudentFace.id == face_id, StudentFace.student_id == student_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Face not found")
    await db.delete(row)
    await db.commit()
    await invalidate_section_cache(db, student_id)
    return MessageResponse(message="Face deleted")


@router.delete("/{student_id}", response_model=MessageResponse)
async def delete_student(student_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Student not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Student deleted")
