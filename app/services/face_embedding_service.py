from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np
from fastapi import HTTPException, UploadFile

from app.core.insight_face import get_face_app

logger = logging.getLogger(__name__)


@dataclass
class FaceEmbeddingAnalysis:
    embedding: np.ndarray        # 512-d ArcFace embedding, L2-normalised
    quality_score: float
    blur_score: float
    brightness_score: float
    face_bbox: dict[str, int] | None


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _image_quality(image: np.ndarray) -> tuple[float, float]:
    """Return (blur_score, brightness_score) for the full image."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray))
    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    blur_score = _clamp(1.0 - (laplacian_var / 250.0))
    brightness_score = _clamp(1.0 - abs(brightness - 135.0) / 135.0)
    return blur_score, brightness_score


async def analyze_face_upload(file: UploadFile) -> FaceEmbeddingAnalysis:
    content = await file.read()
    await file.seek(0)

    if not content:
        raise HTTPException(status_code=400, detail="Uploaded face image is empty")

    buffer = np.frombuffer(content, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")

    blur_score, brightness_score = _image_quality(image)

    face_app = get_face_app()
    faces = face_app.get(image)

    if not faces:
        raise HTTPException(
            status_code=422,
            detail="No face detected in the uploaded image. Please upload a clear, front-facing photo.",
        )

    # Pick the face with the highest detection confidence
    face = max(faces, key=lambda f: float(f.det_score))

    bbox_arr = face.bbox.astype(int)
    face_bbox = {
        "x": int(bbox_arr[0]),
        "y": int(bbox_arr[1]),
        "w": int(bbox_arr[2] - bbox_arr[0]),
        "h": int(bbox_arr[3] - bbox_arr[1]),
    }

    sharpness_score = 1.0 - blur_score
    quality_score = _clamp(
        float(face.det_score) * 0.50
        + sharpness_score * 0.30
        + brightness_score * 0.20
    )

    embedding = np.array(face.embedding, dtype=np.float32)
    # Ensure L2-normalised (InsightFace already normalises, but be explicit)
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm

    return FaceEmbeddingAnalysis(
        embedding=embedding,
        quality_score=round(quality_score, 4),
        blur_score=round(blur_score, 4),
        brightness_score=round(brightness_score, 4),
        face_bbox=face_bbox,
    )
