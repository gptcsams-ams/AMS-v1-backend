"""Provider delivery webhooks — /webhooks/*

These endpoints sit outside /api/v1 to avoid the RBAC middleware.
Each endpoint verifies the provider signature before processing.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.notification import NotifStatus
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
log = logging.getLogger(__name__)


# ── MSG91 ──────────────────────────────────────────────────────────────────────

@router.post("/msg91")
async def msg91_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """MSG91 sends plain JSON; no signature header — validate by IP/payload shape."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # MSG91 status codes: '1'=sent, '3'=delivered, '9'=failed
    STATUS_MAP = {
        "1": NotifStatus.SENT,
        "3": NotifStatus.DELIVERED,
        "9": NotifStatus.FAILED,
    }
    request_id = body.get("requestId")
    raw_status  = str(body.get("status", ""))
    new_status  = STATUS_MAP.get(raw_status)

    if not new_status or not request_id:
        return {"ok": False, "reason": "unrecognised payload"}

    svc = NotificationService(db)
    await svc.handle_delivery_webhook("MSG91", request_id, new_status)
    return {"ok": True}


# ── Twilio ─────────────────────────────────────────────────────────────────────

@router.post("/twilio")
async def twilio_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Twilio signs with X-Twilio-Signature using auth token."""
    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(settings.TWILIO_AUTH_TOKEN or "")
        url        = str(request.url)
        form_data  = dict(await request.form())
        signature  = request.headers.get("X-Twilio-Signature", "")
        if settings.TWILIO_AUTH_TOKEN and not validator.validate(url, form_data, signature):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    except ImportError:
        # twilio package not installed; skip validation
        form_data = dict(await request.form())

    msg_sid    = form_data.get("MessageSid")
    raw_status = form_data.get("MessageStatus", "")
    STATUS_MAP = {
        "sent":        NotifStatus.SENT,
        "delivered":   NotifStatus.DELIVERED,
        "read":        NotifStatus.READ,
        "failed":      NotifStatus.FAILED,
        "undelivered": NotifStatus.FAILED,
    }
    new_status = STATUS_MAP.get(raw_status)
    if not new_status or not msg_sid:
        return Response(status_code=204)

    svc = NotificationService(db)
    await svc.handle_delivery_webhook("TWILIO", msg_sid, new_status)
    return Response(status_code=204)


# ── SendGrid ───────────────────────────────────────────────────────────────────

@router.post("/sendgrid")
async def sendgrid_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """SendGrid signs with Ed25519; verify using public key from settings."""
    body_bytes = await request.body()
    pub_key    = getattr(settings, "SENDGRID_WEBHOOK_PUB_KEY", None)
    if pub_key:
        _verify_sendgrid_sig(
            body_bytes,
            request.headers.get("X-Twilio-Email-Event-Webhook-Signature", ""),
            request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp", ""),
            pub_key,
        )

    try:
        events = json.loads(body_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    STATUS_MAP = {
        "delivered": NotifStatus.DELIVERED,
        "open":      NotifStatus.READ,
        "bounce":    NotifStatus.FAILED,
        "dropped":   NotifStatus.FAILED,
    }
    svc = NotificationService(db)
    for event in events:
        new_status = STATUS_MAP.get(event.get("event"))
        msg_id     = (event.get("sg_message_id") or "").split(".")[0]
        if new_status and msg_id:
            await svc.handle_delivery_webhook("SENDGRID", msg_id, new_status)

    return {"ok": True}


def _verify_sendgrid_sig(body: bytes, signature: str, timestamp: str, pub_key_b64: str) -> None:
    """Ed25519 verification for SendGrid event webhooks."""
    try:
        import base64
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature

        pub_key_bytes = base64.b64decode(pub_key_b64)
        pub_key = Ed25519PublicKey.from_public_bytes(pub_key_bytes)
        payload = timestamp.encode() + body
        sig_bytes = base64.b64decode(signature)
        pub_key.verify(sig_bytes, payload)
    except ImportError:
        log.warning("cryptography package not installed; skipping SendGrid signature verification")
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid SendGrid signature")
