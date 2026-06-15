from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import delete as sa_delete, select, text
from sqlalchemy.exc import IntegrityError
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
from app.services.embedding_cache_service import invalidate_student_in_all_sections
from app.services.face_embedding_service import analyze_face_upload
from app.services.imagekit_service import upload_imagekit_file
from app.services.student_service import import_students_csv

router = APIRouter()


async def _query_students(
    db: AsyncSession,
    section_id: str | None = None,
    year_id: str | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 200,
) -> list[dict]:
    offset = (page - 1) * limit
    filters = ["s.is_active = TRUE"]
    params: dict = {"limit": limit, "offset": offset}

    if section_id and year_id:
        filters.append(
            "EXISTS (SELECT 1 FROM student_enrollments se "
            "WHERE se.student_id = s.id AND se.section_id = CAST(:section_id AS uuid) "
            "AND se.academic_year_id = CAST(:year_id AS uuid) AND se.status = 'ACTIVE')"
        )
        params["section_id"] = section_id
        params["year_id"] = year_id
    elif section_id:
        filters.append(
            "EXISTS (SELECT 1 FROM student_enrollments se "
            "WHERE se.student_id = s.id AND se.section_id = CAST(:section_id AS uuid) "
            "AND se.status = 'ACTIVE')"
        )
        params["section_id"] = section_id
    elif year_id:
        filters.append(
            "EXISTS (SELECT 1 FROM student_enrollments se "
            "WHERE se.student_id = s.id AND se.academic_year_id = CAST(:year_id AS uuid) "
            "AND se.status = 'ACTIVE')"
        )
        params["year_id"] = year_id

    if search:
        filters.append(
            "(s.first_name ILIKE :search OR s.last_name ILIKE :search "
            "OR s.admission_number ILIKE :search)"
        )
        params["search"] = f"%{search}%"

    where_clause = " AND ".join(filters)

    rows = await db.execute(text(f"""
        SELECT
            s.id::text,
            s.first_name,
            s.last_name,
            s.admission_number,
            s.roll_number,
            s.student_photo_url,
            s.is_active,
            s.gender,
            s.blood_group,
            s.dob,
            s.contact_number,
            s.email,
            s.group_name,
            s.branch_id::text,
            s.join_date,
            s.created_at,
            COALESCE(sec.id::text, '')     AS section_id,
            COALESCE(sec.name, '')         AS section_name,
            COALESCE(c.id::text, '')       AS class_id,
            COALESCE(c.grade, '')          AS grade,
            COALESCE(fc.face_count, 0)     AS face_count,
            fc.face_image_url              AS face_image_url,
            COALESCE(att.present, 0)       AS total_present,
            COALESCE(att.total, 0)         AS total_days,
            CASE
                WHEN COALESCE(att.total, 0) = 0 THEN 0.0
                ELSE ROUND(att.present::numeric / att.total * 100, 1)
            END                            AS overall_attendance_pct
        FROM students s
        LEFT JOIN sections sec ON sec.id = (
            SELECT section_id FROM student_enrollments
            WHERE student_id = s.id AND status = 'ACTIVE'
            ORDER BY created_at DESC LIMIT 1
        )
        LEFT JOIN classes c ON c.id = sec.class_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS face_count, MIN(image_url) AS face_image_url
            FROM student_faces sf
            WHERE sf.student_id = s.id AND sf.is_active = TRUE
        ) fc ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) FILTER (WHERE status IN ('PRESENT','LATE')) AS present,
                COUNT(*)                                               AS total
            FROM attendance a
            WHERE a.student_id = s.id
              {("AND a.academic_year_id = CAST(:year_id AS uuid)" if year_id else "")}
        ) att ON TRUE
        WHERE {where_clause}
        ORDER BY s.first_name, s.last_name
        LIMIT :limit OFFSET :offset
    """), params)

    return [dict(r) for r in rows.mappings().fetchall()]


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

    from app.models.section import Section
    from app.models.academic_class import AcademicClass

    enrollment_rows = await db.execute(
        select(StudentEnrollment.student_id, Section.id, Section.class_id, Section.name, AcademicClass.grade)
        .join(Section, StudentEnrollment.section_id == Section.id)
        .join(AcademicClass, Section.class_id == AcademicClass.id)
        .where(StudentEnrollment.student_id.in_(student_ids), StudentEnrollment.status == "ACTIVE")
    )

    sections_by_student: dict[UUID, dict] = {}
    for student_id, section_id, class_id, name, grade in enrollment_rows.all():
        sections_by_student[student_id] = {
            "id": section_id,
            "class_id": class_id,
            "name": name,
            "grade": grade,
        }

    return [
        {
            **StudentResponse.model_validate(student).model_dump(),
            "face_count": face_counts.get(student.id, 0),
            "face_image_url": face_images.get(student.id),
            "section": sections_by_student.get(student.id),
        }
        for student in students
    ]


@router.get("")
async def list_students(
    section_id: UUID | None = Query(default=None),
    year_id: UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _query_students(
        db=db,
        section_id=str(section_id) if section_id else None,
        year_id=str(year_id) if year_id else None,
        search=search,
        page=page,
        limit=limit,
    )


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
    section_id = data.pop("section_id", None)
    academic_year_id = data.pop("academic_year_id", None)
    enrolled_at = data.pop("enrolled_at", None)
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

    try:
        await db.flush()

        if section_id and academic_year_id:
            existing_roll = (await db.execute(
                select(StudentEnrollment).where(
                    StudentEnrollment.section_id == section_id,
                    StudentEnrollment.academic_year_id == academic_year_id,
                    StudentEnrollment.roll_number == payload.roll_number,
                )
            )).scalar_one_or_none()
            if existing_roll:
                raise HTTPException(
                    status_code=409,
                    detail=f"Roll number '{payload.roll_number}' already exists in this section for the selected academic year.",
                )

            db.add(StudentEnrollment(
                student_id=row.id,
                section_id=section_id,
                academic_year_id=academic_year_id,
                roll_number=payload.roll_number,
                enrolled_at=enrolled_at or payload.join_date,
            ))

        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Could not add student. Please check the selected class, section, and academic year.")

    await db.refresh(row)
    return (await _with_face_summary(db, [row]))[0]


@router.post("/bulk-import")
async def bulk_import_students(
    file: UploadFile = File(...),
    academic_year_id: UUID | None = Form(default=None),
    current_user: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await file.read()
    return await import_students_csv(
        db,
        data.decode("utf-8"),
        academic_year_id,
        getattr(current_user, "branch_id", None),
    )


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
    await invalidate_student_in_all_sections(str(student_id), db)
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
async def update_student(
    student_id: UUID,
    payload: StudentUpdate,
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Student not found")

    # Pop enrollment fields so they are NOT passed to the Student model
    data = payload.model_dump(exclude_unset=True)
    section_id = data.pop("section_id", None)
    academic_year_id = data.pop("academic_year_id", None)
    roll_number = data.pop("roll_number", None)

    # Update core student fields
    for key, value in data.items():
        setattr(row, key, value)

    # Sync roll_number on student record
    if roll_number is not None:
        row.roll_number = roll_number

    from sqlalchemy import func

    # Case 1: Both section + year provided → upsert enrollment
    if section_id and academic_year_id:
        target_roll = roll_number or row.roll_number

        # Ensure roll uniqueness within section+year (exclude self)
        dup = (await db.execute(
            select(StudentEnrollment).where(
                StudentEnrollment.section_id == section_id,
                StudentEnrollment.academic_year_id == academic_year_id,
                StudentEnrollment.roll_number == target_roll,
                StudentEnrollment.student_id != student_id,
            )
        )).scalar_one_or_none()
        if dup:
            raise HTTPException(
                status_code=409,
                detail=f"Roll number '{target_roll}' already exists in this section for the selected academic year.",
            )

        enrollment = (await db.execute(
            select(StudentEnrollment).where(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.academic_year_id == academic_year_id,
            )
        )).scalar_one_or_none()

        if enrollment:
            enrollment.section_id = section_id
            enrollment.roll_number = target_roll
        else:
            db.add(StudentEnrollment(
                student_id=row.id,
                section_id=section_id,
                academic_year_id=academic_year_id,
                roll_number=target_roll,
                enrolled_at=row.join_date or func.current_date(),
            ))

    # Case 2: Only roll_number provided → update existing active enrollment
    elif roll_number is not None:
        active = (await db.execute(
            select(StudentEnrollment)
            .where(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status == "ACTIVE",
            )
            .order_by(StudentEnrollment.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        if active:
            dup = (await db.execute(
                select(StudentEnrollment).where(
                    StudentEnrollment.section_id == active.section_id,
                    StudentEnrollment.academic_year_id == active.academic_year_id,
                    StudentEnrollment.roll_number == roll_number,
                    StudentEnrollment.student_id != student_id,
                )
            )).scalar_one_or_none()
            if dup:
                raise HTTPException(
                    status_code=409,
                    detail=f"Roll number '{roll_number}' already exists in this section.",
                )
            active.roll_number = roll_number

    # Case 3: No enrollment fields → only student core fields updated above

    await db.commit()
    await db.refresh(row)
    return (await _with_face_summary(db, [row]))[0]


@router.delete("/{student_id}/faces/{face_id}", response_model=MessageResponse)
async def delete_face(student_id: UUID, face_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(StudentFace).where(StudentFace.id == face_id, StudentFace.student_id == student_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Face not found")
    await db.delete(row)
    await db.commit()
    await invalidate_student_in_all_sections(str(student_id), db)
    return MessageResponse(message="Face deleted")


@router.delete("/{student_id}", response_model=MessageResponse)
async def delete_student(student_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Student not found")
    # Use a core DELETE so PostgreSQL handles FK cascades (CASCADE / SET NULL) directly,
    # avoiding async lazy-load errors that occur when the ORM tries to cascade through
    # relationships (enrollments, faces, attendance_records, etc.) before deleting.
    await db.execute(sa_delete(Student).where(Student.id == student_id))
    await db.commit()
    return MessageResponse(message="Student deleted")
