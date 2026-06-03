from __future__ import annotations

import asyncio
from typing import Any

import msgpack
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.models.student_enrollment import StudentEnrollment
from app.models.student_face import StudentFace


class EmbeddingCacheService:
    TTL_SECONDS = 24 * 60 * 60

    @staticmethod
    async def load_section_embeddings(db: AsyncSession, section_id: str, year_id: str) -> dict[str, list[list[float]]]:
        redis = get_redis()
        key = f"embeddings:{section_id}:{year_id}"
        lock_key = f"lock:embeddings:{section_id}:{year_id}"

        cached = await redis.get(key)
        if cached:
            return msgpack.unpackb(bytes.fromhex(cached), raw=False)

        lock = await redis.set(lock_key, "1", nx=True, ex=30)
        if not lock:
            await asyncio.sleep(0.2)
            cached_retry = await redis.get(key)
            if cached_retry:
                return msgpack.unpackb(bytes.fromhex(cached_retry), raw=False)

        rows = await db.execute(
            select(StudentFace.student_id, StudentFace.embedding)
            .join(StudentEnrollment, StudentEnrollment.student_id == StudentFace.student_id)
            .where(StudentEnrollment.section_id == section_id, StudentEnrollment.academic_year_id == year_id)
        )
        payload: dict[str, list[list[float]]] = {}
        for student_id, embedding in rows.all():
            payload.setdefault(str(student_id), []).append(list(embedding))

        packed = msgpack.packb(payload, use_bin_type=True).hex()
        await redis.setex(key, EmbeddingCacheService.TTL_SECONDS, packed)
        await redis.delete(lock_key)
        return payload


async def invalidate_section_cache(db: AsyncSession, student_id: str) -> None:
    redis = get_redis()
    rows = await db.execute(
        select(StudentEnrollment.section_id, StudentEnrollment.academic_year_id).where(StudentEnrollment.student_id == student_id)
    )
    for section_id, year_id in rows.all():
        await redis.delete(f"embeddings:{section_id}:{year_id}")
