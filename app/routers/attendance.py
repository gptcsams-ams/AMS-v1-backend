from datetime import date
from uuid import UUID

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.core.insight_face import get_face_app
from app.core.redis import get_redis
from app.models.attendance import Attendance
from app.models.attendance_window import AttendanceWindow
from app.models.student import Student
from app.models.student_enrollment import StudentEnrollment
from app.models.student_face import StudentFace
from app.schemas.attendance import AttendanceManualMarkRequest
from app.schemas.common import MessageResponse
from app.schemas.timetable import AttendanceOverride, AttendanceWindowCreate, AttendanceWindowUpdate
from app.services.face_embedding_service import analyze_face_upload

router = APIRouter()


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))


@router.get("/attendance-windows")
async def list_windows(section_id: UUID | None = Query(default=None), _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    stmt = select(AttendanceWindow)
    if section_id:
        stmt = stmt.where(AttendanceWindow.section_id == section_id)
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.post("/attendance-windows")
async def create_window(payload: AttendanceWindowCreate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = AttendanceWindow(**payload.model_dump())
    db.add(row)
    await db.commit()
    return {"id": str(row.id)}


@router.patch("/attendance-windows/{window_id}")
async def update_window(window_id: UUID, payload: AttendanceWindowUpdate, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(AttendanceWindow).where(AttendanceWindow.id == window_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Window not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    return {"message": "Window updated"}


@router.delete("/attendance-windows/{window_id}", response_model=MessageResponse)
async def delete_window(window_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(AttendanceWindow).where(AttendanceWindow.id == window_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Window not found")
    await db.delete(row)
    await db.commit()
    return MessageResponse(message="Window deleted")


@router.get("/attendance")
async def list_attendance(section_id: UUID | None = Query(default=None), _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    stmt = select(Attendance)
    if section_id:
        stmt = stmt.where(Attendance.section_id == section_id)
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.get("/attendance/live/{window_id}")
async def get_live_attendance(window_id: UUID, _: object = Depends(require_admin)):
    redis = get_redis()
    key = f"attendance:live:{window_id}:{date.today().isoformat()}"
    return await redis.hgetall(key)


@router.post("/attendance/detect-faces")
async def detect_faces(
    image: UploadFile = File(...),
    _: object = Depends(require_admin),
):
    """Lightweight InsightFace detection — returns bounding boxes for all detected faces, no DB query."""
    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty image")

    buffer = np.frombuffer(content, dtype=np.uint8)
    img = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image")

    faces = get_face_app().get(img)
    result = []
    for face in faces:
        bbox = face.bbox.astype(int)
        result.append({
            "x": int(bbox[0]),
            "y": int(bbox[1]),
            "w": int(bbox[2] - bbox[0]),
            "h": int(bbox[3] - bbox[1]),
            "score": round(float(face.det_score), 3),
        })
    return {"faces": result, "count": len(result)}


@router.post("/attendance/identify-face")
async def identify_face(
    section_id: UUID = Form(...),
    academic_year_id: UUID = Form(...),
    image: UploadFile = File(...),
    threshold: float = Form(default=0.42),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    analysis = await analyze_face_upload(image)
    captured_embedding = np.asarray(analysis.embedding, dtype=np.float32)

    rows = await db.execute(
        select(Student, StudentFace)
        .join(StudentEnrollment, StudentEnrollment.student_id == Student.id)
        .join(StudentFace, StudentFace.student_id == Student.id)
        .where(
            StudentEnrollment.section_id == section_id,
            StudentEnrollment.academic_year_id == academic_year_id,
            Student.is_active == True,
            StudentFace.is_active == True,
        )
    )

    best_student: Student | None = None
    best_face: StudentFace | None = None
    best_score = 0.0

    for student, face in rows.all():
        if face.embedding is None:
            continue
        score = _cosine_similarity(captured_embedding, np.asarray(face.embedding, dtype=np.float32))
        if score > best_score:
            best_score = score
            best_student = student
            best_face = face

    if not best_student or not best_face or best_score < threshold:
        return {
            "matched": False,
            "confidence": round(best_score, 4),
            "threshold": threshold,
            "capture_quality": analysis.quality_score,
            "face_bbox": analysis.face_bbox,
            "message": "No enrolled student matched this camera image.",
        }

    return {
        "matched": True,
        "confidence": round(best_score, 4),
        "threshold": threshold,
        "capture_quality": analysis.quality_score,
        "face_bbox": analysis.face_bbox,
        "student": {
            "id": str(best_student.id),
            "first_name": best_student.first_name,
            "last_name": best_student.last_name,
            "admission_number": best_student.admission_number,
            "roll_number": best_student.roll_number,
            "student_photo_url": best_student.student_photo_url,
            "face_image_url": best_face.image_url,
            "face_quality": best_face.quality_score,
        },
    }


@router.patch("/attendance/{attendance_id}/override")
async def override_attendance(attendance_id: UUID, payload: AttendanceOverride, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Attendance).where(Attendance.id == attendance_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    row.status = payload.status
    row.is_overridden = True
    row.override_reason = payload.reason
    row.marked_by = "ADMIN"
    await db.commit()
    return {"message": "Attendance overridden"}


@router.post("/attendance/mark-manual")
async def mark_manual(payload: AttendanceManualMarkRequest, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = Attendance(
        student_id=payload.student_id,
        section_id=payload.section_id,
        academic_year_id=payload.academic_year_id,
        attendance_window_id=payload.attendance_window_id,
        attendance_date=payload.attendance_date.date(),
        status=payload.status,
        marked_by="TEACHER",
        is_overridden=True,
    )
    db.add(row)
    await db.commit()
    return {"id": str(row.id)}


@router.get("/attendance/report/student/{student_id}")
async def student_report(student_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Attendance).where(Attendance.student_id == student_id))
    return list(rows.scalars().all())


@router.get("/attendance/report/section/{section_id}")
async def section_report(section_id: UUID, _: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Attendance).where(Attendance.section_id == section_id))
    return list(rows.scalars().all())


@router.get("/attendance/report/defaulters")
async def defaulters_report(_: object = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Attendance).where(Attendance.status == "ABSENT"))
    return list(rows.scalars().all())
