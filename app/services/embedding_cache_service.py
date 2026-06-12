from __future__ import annotations

import asyncio
import logging
from typing import Any

import msgpack
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.models.student_enrollment import StudentEnrollment
from app.models.student_face import StudentFace

logger = logging.getLogger(__name__)


class EmbeddingCacheService:
    TTL_SECONDS = 24 * 60 * 60

    @staticmethod
    async def load_section_embeddings(db: AsyncSession, section_id: str, year_id: str) -> dict[str, list[list[float]]]:
        key = f"embeddings:{section_id}:{year_id}"
        lock_key = f"lock:embeddings:{section_id}:{year_id}"

        redis = None
        try:
            redis = get_redis()
            cached = await redis.get(key)
            if cached:
                return msgpack.unpackb(bytes.fromhex(cached), raw=False)

            lock = await redis.set(lock_key, "1", nx=True, ex=30)
            if not lock:
                await asyncio.sleep(0.2)
                cached_retry = await redis.get(key)
                if cached_retry:
                    return msgpack.unpackb(bytes.fromhex(cached_retry), raw=False)
        except (RedisError, RuntimeError) as exc:
            logger.warning("Embedding cache unavailable; loading from database: %s", exc)

        rows = await db.execute(
            select(StudentFace.student_id, StudentFace.embedding)
            .join(StudentEnrollment, StudentEnrollment.student_id == StudentFace.student_id)
            .where(StudentEnrollment.section_id == section_id, StudentEnrollment.academic_year_id == year_id)
        )
        payload: dict[str, list[list[float]]] = {}
        for student_id, embedding in rows.all():
            payload.setdefault(str(student_id), []).append(list(embedding))

        packed = msgpack.packb(payload, use_bin_type=True).hex()
        if redis is not None:
            try:
                await redis.setex(key, EmbeddingCacheService.TTL_SECONDS, packed)
                await redis.delete(lock_key)
            except RedisError as exc:
                logger.warning("Embedding cache write skipped: %s", exc)
        return payload


async def invalidate_section_cache(db: AsyncSession, student_id: str) -> None:
    rows = await db.execute(
        select(StudentEnrollment.section_id, StudentEnrollment.academic_year_id).where(StudentEnrollment.student_id == student_id)
    )
    enrollments = rows.all()
    if not enrollments:
        return

    try:
        redis = get_redis()
        for section_id, year_id in enrollments:
            await redis.delete(f"embeddings:{section_id}:{year_id}")
    except (RedisError, RuntimeError) as exc:
        logger.warning("Embedding cache invalidation skipped: %s", exc)
