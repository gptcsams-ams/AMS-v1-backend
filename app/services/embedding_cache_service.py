"""
Embedding Cache — Three levels:
  L1: Python dict in process memory  (recognition, 0ms)
  L2: .npy files on disk             (warm restart, <5ms)
  L3: PostgreSQL pgvector             (source of truth, ~200ms Neon)

Recognition uses L1 only — no DB, no file I/O per frame.
Files updated only when student faces change.
"""

import numpy as np
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import settings

log = logging.getLogger(__name__)

# L1: process memory
_cache: Dict[str, dict] = {}
_locks: Dict[str, asyncio.Lock] = {}

# L2: disk
EMBED_DIR   = Path(settings.MEDIA_ROOT) / "embeddings"
STALE_HOURS = 24
EMBED_DIR.mkdir(parents=True, exist_ok=True)


async def get_section_embeddings(
    section_id: str,
    academic_year_id: str,
    db: AsyncSession,
) -> Tuple[np.ndarray, list]:
    """
    Returns (embeddings_array shape (N,512), student_ids list len N).
    Load order: L1 → L2 → L3.
    """
    key = f"{section_id}:{academic_year_id}"

    if key in _cache:
        return _cache[key]["embeddings"], _cache[key]["student_ids"]

    if key not in _locks:
        _locks[key] = asyncio.Lock()

    async with _locks[key]:
        if key in _cache:
            return _cache[key]["embeddings"], _cache[key]["student_ids"]

        embs, ids = _load_disk(section_id, academic_year_id)
        if embs is not None:
            _cache[key] = {"embeddings": embs, "student_ids": ids}
            log.info(f"[emb] disk  section={section_id[:8]} n={len(ids)}")
            return embs, ids

        embs, ids = await _load_db(section_id, academic_year_id, db)
        if embs is not None:
            _save_disk(section_id, academic_year_id, embs, ids)
        else:
            embs = np.empty((0, 512), dtype=np.float32)
            ids  = []
            log.warning(f"[emb] empty section={section_id[:8]}")

        _cache[key] = {"embeddings": embs, "student_ids": ids}
        log.info(f"[emb] db    section={section_id[:8]} n={len(ids)}")
        return embs, ids


async def invalidate_section(
    section_id: str,
    academic_year_id: str,
    db: AsyncSession,
):
    """Reload from DB → update disk → update L1. Call after any StudentFace change."""
    key = f"{section_id}:{academic_year_id}"
    log.info(f"[emb] invalidate section={section_id[:8]}")

    embs, ids = await _load_db(section_id, academic_year_id, db)
    if embs is None:
        embs = np.empty((0, 512), dtype=np.float32)
        ids  = []

    _save_disk(section_id, academic_year_id, embs, ids)
    _cache[key] = {"embeddings": embs, "student_ids": ids}
    log.info(f"[emb] refreshed section={section_id[:8]} n={len(ids)}")


async def invalidate_student_in_all_sections(student_id: str, db: AsyncSession):
    """Call when a student's face changes and caller doesn't know the section."""
    result = await db.execute(text("""
        SELECT section_id::text, academic_year_id::text
        FROM student_enrollments
        WHERE student_id = :sid AND status = 'ACTIVE'
    """), {"sid": student_id})
    for section_id, year_id in result.fetchall():
        await invalidate_section(section_id, year_id, db)


async def load_all_sections_on_startup(db: AsyncSession):
    """Load all active sections at startup so first recognition request doesn't cold-load."""
    log.info("[emb] startup preload...")
    result = await db.execute(text("""
        SELECT DISTINCT
            se.section_id::text,
            se.academic_year_id::text
        FROM student_enrollments se
        JOIN academic_years ay ON ay.id = se.academic_year_id
        WHERE se.status = 'ACTIVE' AND ay.is_current = TRUE
    """))
    rows   = result.fetchall()
    loaded = 0
    for sid, yid in rows:
        try:
            await get_section_embeddings(sid, yid, db)
            loaded += 1
        except Exception as e:
            log.error(f"[emb] preload failed {sid[:8]}: {e}")
    log.info(f"[emb] preload done {loaded}/{len(rows)} sections")


def evict_section(section_id: str, academic_year_id: str):
    """Remove from L1 when window closes (optional memory cleanup)."""
    _cache.pop(f"{section_id}:{academic_year_id}", None)


def get_cache_stats() -> dict:
    return {
        "sections_loaded": len(_cache),
        "total_students":  sum(len(v["student_ids"]) for v in _cache.values()),
        "memory_mb":       round(
            sum(v["embeddings"].nbytes for v in _cache.values()) / 1_048_576, 2
        ),
    }


# ── Internal ──────────────────────────────────────────────────────────────────

async def _load_db(
    section_id: str,
    academic_year_id: str,
    db: AsyncSession,
) -> Tuple[Optional[np.ndarray], list]:
    result = await db.execute(text("""
        SELECT sf.student_id::text, sf.embedding
        FROM student_faces sf
        INNER JOIN student_enrollments se
               ON se.student_id       = sf.student_id
              AND se.section_id       = :sid
              AND se.academic_year_id = :yid
              AND se.status           = 'ACTIVE'
        WHERE sf.is_active = TRUE
        ORDER BY sf.student_id, sf.created_at DESC
    """), {"sid": section_id, "yid": academic_year_id})
    rows = result.fetchall()

    if not rows:
        return None, []

    grouped: Dict[str, list] = {}
    for student_id, embedding in rows:
        if isinstance(embedding, str):
            embedding = json.loads(embedding)
        vec  = np.array(embedding, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        grouped.setdefault(student_id, []).append(vec)

    ids, avgs = [], []
    for sid, embs in grouped.items():
        avg  = np.mean(embs, axis=0)
        norm = np.linalg.norm(avg)
        if norm > 0:
            avg = avg / norm
        ids.append(sid)
        avgs.append(avg)

    return np.stack(avgs).astype(np.float32), ids


def _load_disk(section_id: str, academic_year_id: str) -> Tuple[Optional[np.ndarray], list]:
    emb  = EMBED_DIR / f"{section_id}_{academic_year_id}.npy"
    ids  = EMBED_DIR / f"{section_id}_{academic_year_id}_ids.npy"
    meta = EMBED_DIR / f"{section_id}_{academic_year_id}_meta.json"

    if not (emb.exists() and ids.exists()):
        return None, []

    try:
        if meta.exists():
            m   = json.loads(meta.read_text())
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(m["updated_at"])).total_seconds() / 3600
            if age > STALE_HOURS:
                log.info(f"[emb] stale disk ({age:.0f}h) {section_id[:8]}")
                return None, []
        return (
            np.load(str(emb)).astype(np.float32),
            np.load(str(ids), allow_pickle=True).tolist(),
        )
    except Exception as e:
        log.warning(f"[emb] disk read failed {section_id[:8]}: {e}")
        return None, []


def _save_disk(section_id: str, academic_year_id: str, embeddings: np.ndarray, student_ids: list):
    try:
        np.save(str(EMBED_DIR / f"{section_id}_{academic_year_id}.npy"), embeddings)
        np.save(str(EMBED_DIR / f"{section_id}_{academic_year_id}_ids.npy"),
                np.array(student_ids, dtype=object))
        (EMBED_DIR / f"{section_id}_{academic_year_id}_meta.json").write_text(
            json.dumps({
                "updated_at":    datetime.now(timezone.utc).isoformat(),
                "student_count": len(student_ids),
            }, indent=2)
        )
    except Exception as e:
        log.error(f"[emb] disk write failed {section_id[:8]}: {e}")


# ── Legacy class shim — keeps existing section_worker.py import working ───────

class EmbeddingCacheService:
    """Backwards-compat shim for cv_worker/section_worker.py."""

    @staticmethod
    async def load_section_embeddings(
        db: AsyncSession,
        section_id: str,
        academic_year_id: str,
    ) -> Dict[str, list]:
        embs, ids = await get_section_embeddings(section_id, academic_year_id, db)
        if len(ids) == 0:
            return {}
        return {sid: [embs[i].tolist()] for i, sid in enumerate(ids)}
