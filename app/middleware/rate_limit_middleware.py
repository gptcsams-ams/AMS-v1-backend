import time
from typing import Callable

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import settings
from app.core.redis import get_redis


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        try:
            redis = get_redis()
            ident = request.client.host if request.client else "unknown"
            window = int(time.time() // 60)
            key = f"rate:{ident}:{window}"
            current = await redis.incr(key)
            if current == 1:
                await redis.expire(key, 60)
            if current > settings.RATE_LIMIT_PER_MINUTE:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
        except HTTPException:
            raise
        except Exception:
            # Redis is optional in local development; do not block auth/API requests.
            pass
        return await call_next(request)
