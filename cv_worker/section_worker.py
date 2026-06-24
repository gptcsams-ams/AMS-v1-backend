from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from functools import partial
from uuid import UUID

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.attendance_window import AttendanceWindow
from app.models.camera import Camera
from app.models.student_enrollment import StudentEnrollment
from app.services.attendance_service import upsert_attendance
from app.services.embedding_cache_service import (
    EmbeddingCacheService,
    get_section_embeddings,
    evict_section,
)
from cv_worker.face_detector import detect_faces
from cv_worker.face_matcher import match_face

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now()


def _combine(d: date, t) -> datetime:
    return datetime.combine(d, t)


def _open_capture(rtsp_url: str) -> cv2.VideoCapture:
    """Open a VideoCapture for an RTSP URL or a local webcam.

    Use rtsp_url = "webcam:0" (or "webcam:1" etc.) for local cameras during testing.
    Use a real rtsp:// URL for CCTV.
    """
    if rtsp_url.startswith("webcam:"):
        index = int(rtsp_url.split(":")[1])
        cap = cv2.VideoCapture(index)
    else:
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    return cap


def _grab_frame(cap: cv2.VideoCapture) -> np.ndarray | None:
    """Grab a single frame from an open VideoCapture. Returns None on failure."""
    ret, frame = cap.read()
    if not ret or frame is None:
        return None
    return frame


# ──────────────────────────────────────────────
# Burst runner
# ──────────────────────────────────────────────

async def _run_burst(
    *,
    cap: cv2.VideoCapture,
    end_time: datetime,
    interval_secs: int,
    embeddings: np.ndarray,
    student_ids: list,
    window: AttendanceWindow,
    section_id: UUID,
    academic_year_id: UUID,
    attendance_date: date,
    threshold: float,
) -> None:
    """Grab frames at `interval_secs` until `end_time`, detect and match faces."""
    loop = asyncio.get_running_loop()

    while _now() < end_time:
        frame = await loop.run_in_executor(None, partial(_grab_frame, cap))

        if frame is None:
            logger.warning("window=%s — failed to grab frame, skipping", window.id)
        else:
            detected = await loop.run_in_executor(None, partial(detect_faces, frame))
            logger.debug("window=%s — %d face(s) detected in frame", window.id, len(detected))

            async with AsyncSessionLocal() as db:
                for face in detected:
                    student_id, score, status = match_face(
                        query_embedding=face.normed_embedding,
                        embeddings=embeddings,
                        student_ids=student_ids,
                        threshold=threshold,
                    )
                    if status == "UNKNOWN" or student_id is None:
                        continue

                    await upsert_attendance(
                        db,
                        student_id=UUID(student_id),
                        section_id=section_id,
                        academic_year_id=academic_year_id,
                        attendance_window_id=window.id,
                        attendance_date=attendance_date,
                        detected_at=_now(),
                        status="PRESENT",
                        data_confidence="LOW" if status == "LOW_CONFIDENCE" else "HIGH",
                    )
                    logger.info(
                        "window=%s student=%s score=%.3f status=%s",
                        window.id, student_id, score, status,
                    )

        remaining = (end_time - _now()).total_seconds()
        await asyncio.sleep(min(interval_secs, max(0, remaining)))


# ──────────────────────────────────────────────
# Section worker entry point
# ──────────────────────────────────────────────

async def run_section_window(
    window: AttendanceWindow,
    camera: Camera,
    academic_year_id: UUID,
    attendance_date: date,
) -> None:
    """
    State machine for one AttendanceWindow + Camera pair.

    Timeline:
      start_time + detection_start_offset_minutes  → BURST 1 starts
      burst1_start + opening_capture_duration_minutes → BURST 1 ends
                        ... IDLE ...
      end_time - closing_capture_duration_minutes   → BURST 2 starts
      end_time                                      → BURST 2 ends, finalize
    """
    today = attendance_date
    burst1_start = _combine(today, window.start_time) + timedelta(
        minutes=window.detection_start_offset_minutes
    )
    burst1_end = burst1_start + timedelta(minutes=window.opening_capture_duration_minutes)
    burst2_start = _combine(today, window.end_time) - timedelta(
        minutes=window.closing_capture_duration_minutes
    )
    burst2_end = _combine(today, window.end_time)
    interval = camera.frame_sample_interval_secs

    logger.info(
        "section_worker started | window=%s camera=%s | "
        "burst1=%s→%s  burst2=%s→%s  interval=%ds",
        window.id, camera.id,
        burst1_start.strftime("%H:%M:%S"), burst1_end.strftime("%H:%M:%S"),
        burst2_start.strftime("%H:%M:%S"), burst2_end.strftime("%H:%M:%S"),
        interval,
    )

    # Load embeddings for this section once (L1 cache → disk → DB)
    async with AsyncSessionLocal() as db:
        emb_matrix, student_ids = await get_section_embeddings(
            section_id=str(window.section_id),
            academic_year_id=str(academic_year_id),
            db=db,
        )

    if len(student_ids) == 0:
        logger.warning("window=%s — no enrolled student embeddings found, aborting", window.id)
        return

    # Open video source (kept open for both bursts)
    cap = _open_capture(camera.rtsp_url)
    if not cap.isOpened():
        logger.error("window=%s — could not open stream: %s", window.id, camera.rtsp_url)
        return

    try:
        # ── IDLE until burst 1 ──────────────────────────────────────────
        wait = (burst1_start - _now()).total_seconds()
        if wait > 0:
            logger.info("window=%s — waiting %.0fs for burst 1", window.id, wait)
            await asyncio.sleep(wait)

        # ── BURST 1 ─────────────────────────────────────────────────────
        if _now() < burst1_end:
            logger.info("window=%s — BURST 1 started", window.id)
            await _run_burst(
                cap=cap,
                end_time=burst1_end,
                interval_secs=interval,
                embeddings=emb_matrix,
                student_ids=student_ids,
                window=window,
                section_id=window.section_id,
                academic_year_id=academic_year_id,
                attendance_date=today,
                threshold=window.confidence_threshold,
            )
            logger.info("window=%s — BURST 1 ended", window.id)

        # ── IDLE until burst 2 ──────────────────────────────────────────
        wait = (burst2_start - _now()).total_seconds()
        if wait > 0:
            logger.info("window=%s — idle for %.0fs until burst 2", window.id, wait)
            await asyncio.sleep(wait)

        # ── BURST 2 ─────────────────────────────────────────────────────
        if _now() < burst2_end:
            logger.info("window=%s — BURST 2 started", window.id)
            await _run_burst(
                cap=cap,
                end_time=burst2_end,
                interval_secs=interval,
                embeddings=emb_matrix,
                student_ids=student_ids,
                window=window,
                section_id=window.section_id,
                academic_year_id=academic_year_id,
                attendance_date=today,
                threshold=window.confidence_threshold,
            )
            logger.info("window=%s — BURST 2 ended", window.id)

    except asyncio.CancelledError:
        logger.info("window=%s — worker cancelled", window.id)
        raise
    except Exception:
        logger.exception("window=%s — unhandled error in section_worker", window.id)
    finally:
        cap.release()
        logger.info("window=%s — stream released", window.id)

        # Finalize: mark students below min_detections as ABSENT
        async with AsyncSessionLocal() as db:
            from app.services.attendance_service import finalize_window
            result = await finalize_window(db, window.id, today, academic_year_id)
            logger.info("window=%s — finalized: %s", window.id, result)
        evict_section(str(window.section_id), str(academic_year_id))

        # ── Fire period-attendance emails — NON-BLOCKING ─────────────────────
        # asyncio.create_task() returns immediately; the email task runs in the
        # background on the event loop so the next period's window opens on time.
        # The task owns its own DB session (created here, closed inside the task).
        from app.services.email_service import send_period_attendance_emails
        asyncio.create_task(
            send_period_attendance_emails(
                window_id=str(window.id),
                db=AsyncSessionLocal(),
            )
        )


def now_utc() -> datetime:
    return datetime.utcnow()
