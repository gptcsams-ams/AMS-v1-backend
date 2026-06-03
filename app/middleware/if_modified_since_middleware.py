from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class IfModifiedSinceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)
        if request.method == "GET":
            now = datetime.now(timezone.utc)
            response.headers["Last-Modified"] = now.strftime("%a, %d %b %Y %H:%M:%S GMT")
            ims = request.headers.get("if-modified-since")
            if ims:
                try:
                    ims_dt = parsedate_to_datetime(ims)
                    if ims_dt and (now - ims_dt).total_seconds() < 1:
                        response.status_code = 304
                        response.body = b""
                except Exception:
                    pass
        return response
