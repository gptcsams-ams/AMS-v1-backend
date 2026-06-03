import redis.asyncio as aioredis

from app.core.config import settings


redis_client: aioredis.Redis | None = None


async def init_redis() -> None:
    global redis_client
    redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=50,
    )


async def close_redis() -> None:
    if redis_client:
        await redis_client.aclose()


def get_redis() -> aioredis.Redis:
    if redis_client is None:
        raise RuntimeError("Redis client is not initialized")
    return redis_client
