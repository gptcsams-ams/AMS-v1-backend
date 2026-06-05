from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from fastapi import HTTPException, UploadFile


@dataclass
class FaceEmbeddingAnalysis:
    embedding: list[float]
    quality_score: float
    blur_score: float
    brightness_score: float
    face_bbox: dict[str, int] | None


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _normalized_histogram_embedding(image: np.ndarray) -> list[float]:
    resized = cv2.resize(image, (64, 64), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
    features: list[float] = []

    for channel, bins in ((0, 128), (1, 128), (2, 128)):
        hist = cv2.calcHist([hsv], [channel], None, [bins], [0, 256]).flatten()
        total = float(hist.sum()) or 1.0
        features.extend((hist / total).tolist())

    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    edge = cv2.Canny(gray, 80, 160)
    edge_hist = cv2.calcHist([edge], [0], None, [128], [0, 256]).flatten()
    edge_total = float(edge_hist.sum()) or 1.0
    features.extend((edge_hist / edge_total).tolist())

    vector = features[:512]
    if len(vector) < 512:
        vector.extend([0.0] * (512 - len(vector)))
    return [float(v) for v in vector]


async def analyze_face_upload(file: UploadFile) -> FaceEmbeddingAnalysis:
    content = await file.read()
    await file.seek(0)

    if not content:
        raise HTTPException(status_code=400, detail="Uploaded face image is empty")

    buffer = np.frombuffer(content, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))
    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    blur_score = _clamp(1.0 - (laplacian_var / 250.0))
    sharpness_score = 1.0 - blur_score
    brightness_score = _clamp(1.0 - abs(brightness - 135.0) / 135.0)
    contrast_score = _clamp(contrast / 64.0)

    face_bbox: dict[str, int] | None = None
    face_score = 0.25
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    if not detector.empty():
        faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
        if len(faces) > 0:
            x, y, w, h = max(faces, key=lambda box: int(box[2]) * int(box[3]))
            face_bbox = {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
            area_ratio = (float(w) * float(h)) / float(image.shape[0] * image.shape[1])
            face_size_score = _clamp(area_ratio / 0.18)
            centered_x = abs((x + w / 2) - (image.shape[1] / 2)) / (image.shape[1] / 2)
            centered_y = abs((y + h / 2) - (image.shape[0] / 2)) / (image.shape[0] / 2)
            center_score = _clamp(1.0 - ((centered_x + centered_y) / 2.0))
            face_score = (face_size_score * 0.6) + (center_score * 0.4)

    quality_score = _clamp(
        (sharpness_score * 0.35)
        + (brightness_score * 0.25)
        + (contrast_score * 0.15)
        + (face_score * 0.25)
    )

    return FaceEmbeddingAnalysis(
        embedding=_normalized_histogram_embedding(image),
        quality_score=round(quality_score, 4),
        blur_score=round(blur_score, 4),
        brightness_score=round(brightness_score, 4),
        face_bbox=face_bbox,
    )
