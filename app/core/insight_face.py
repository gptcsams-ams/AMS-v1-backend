from __future__ import annotations

import threading
import logging

from insightface.app import FaceAnalysis

from app.core.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_app: FaceAnalysis | None = None


def get_face_app() -> FaceAnalysis:
    """Return the shared InsightFace FaceAnalysis instance, loading it on first call."""
    global _app
    if _app is None:
        with _lock:
            if _app is None:
                logger.info(
                    "Loading InsightFace model '%s' (ctx_id=%d) — this may take a moment on first run.",
                    settings.INSIGHTFACE_MODEL,
                    settings.INSIGHTFACE_CTX_ID,
                )
                app = FaceAnalysis(
                    name=settings.INSIGHTFACE_MODEL,
                    providers=["CPUExecutionProvider"],
                )
                app.prepare(ctx_id=settings.INSIGHTFACE_CTX_ID, det_size=(960, 960))
                _app = app
                logger.info("InsightFace model loaded.")
    return _app
