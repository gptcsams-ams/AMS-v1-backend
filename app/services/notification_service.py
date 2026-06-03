from __future__ import annotations

from typing import Optional

import httpx

from app.core.config import settings


async def send_whatsapp(to: str, body: str) -> dict:
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_FROM:
        return {"status": "skipped", "reason": "twilio_not_configured"}
    # Placeholder transport hook.
    _ = (to, body)
    return {"status": "queued"}


async def send_sms(to: str, body: str) -> dict:
    if not settings.MSG91_API_KEY:
        return {"status": "skipped", "reason": "msg91_not_configured"}
    headers = {"authkey": settings.MSG91_API_KEY}
    _ = headers
    _ = (to, body)
    return {"status": "queued"}


async def send_email(to: str, subject: str, body: str) -> dict:
    if not settings.SENDGRID_API_KEY:
        return {"status": "skipped", "reason": "sendgrid_not_configured"}
    _ = (to, subject, body)
    return {"status": "queued"}


async def dispatch_notification(channel: str, to: str, message: str, subject: Optional[str] = None) -> dict:
    if channel == "WHATSAPP":
        return await send_whatsapp(to, message)
    if channel == "SMS":
        return await send_sms(to, message)
    if channel == "EMAIL":
        return await send_email(to, subject or "AMS Notification", message)
    return {"status": "unsupported_channel"}
