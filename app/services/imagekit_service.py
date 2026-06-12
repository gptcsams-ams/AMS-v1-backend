import base64
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import HTTPException, UploadFile

from app.core.config import settings


IMAGEKIT_UPLOAD_URL = "https://upload.imagekit.io/api/v1/files/upload"


def _require_imagekit_config() -> tuple[str, str]:
    if not settings.IMAGEKIT_PRIVATE_KEY or not settings.IMAGEKIT_URL_ENDPOINT:
        raise HTTPException(
            status_code=500,
            detail="ImageKit is not configured. Set IMAGEKIT_PRIVATE_KEY and IMAGEKIT_URL_ENDPOINT.",
        )
    return settings.IMAGEKIT_PRIVATE_KEY, settings.IMAGEKIT_URL_ENDPOINT.rstrip("/")


def _safe_file_name(filename: str | None) -> str:
    original = Path(filename or "upload").name
    stem = Path(original).stem or "upload"
    suffix = Path(original).suffix.lower()
    return f"{stem[:80]}-{uuid4().hex}{suffix}"


async def upload_imagekit_file(file: UploadFile, folder: str) -> str:
    private_key, _ = _require_imagekit_config()
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    auth_token = base64.b64encode(f"{private_key}:".encode("utf-8")).decode("ascii")
    data = {
        "fileName": _safe_file_name(file.filename),
        "folder": folder,
        "useUniqueFileName": "true",
    }
    files = {
        "file": (
            file.filename or "upload",
            content,
            file.content_type or "application/octet-stream",
        )
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                IMAGEKIT_UPLOAD_URL,
                data=data,
                files=files,
                headers={"Authorization": f"Basic {auth_token}"},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else "ImageKit upload failed"
        raise HTTPException(status_code=502, detail=f"ImageKit upload failed: {detail}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="ImageKit upload failed") from exc

    payload = response.json()
    image_url = payload.get("url")
    if not image_url:
        raise HTTPException(status_code=502, detail="ImageKit upload response did not include a URL")
    return image_url
