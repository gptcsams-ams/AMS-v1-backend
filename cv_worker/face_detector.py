from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from app.core.insight_face import get_face_app

logger = logging.getLogger(__name__)


@dataclass
class DetectedFace:
    embedding: np.ndarray        # 512-d ArcFace embedding, L2-normalised
    bbox: dict[str, int]         # {x, y, w, h}
    det_score: float


def detect_faces(frame: np.ndarray, min_score: float = 0.50) -> list[DetectedFace]:
    """
    Run InsightFace detection + ArcFace embedding on a single BGR frame.
    Returns one DetectedFace per face that meets min_score.
    """
    face_app = get_face_app()

    try:
        faces = face_app.get(frame)
    except Exception:
        logger.exception("InsightFace inference error on frame")
        return []

    result: list[DetectedFace] = []
    for face in faces:
        score = float(face.det_score)
        if score < min_score:
            continue

        bbox_arr = face.bbox.astype(int)
        embedding = np.array(face.embedding, dtype=np.float32)
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        result.append(
            DetectedFace(
                embedding=embedding,
                bbox={
                    "x": int(bbox_arr[0]),
                    "y": int(bbox_arr[1]),
                    "w": int(bbox_arr[2] - bbox_arr[0]),
                    "h": int(bbox_arr[3] - bbox_arr[1]),
                },
                det_score=score,
            )
        )

    return result
