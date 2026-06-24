"""
Email settings endpoints — CRUD + test send.
All endpoints require ADMIN (or SUPER_ADMIN) role.

Registered in app/main.py with prefix /api/v1/settings/email.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models.email_settings import EmailSettings
from app.models.user import User
from app.services.email_service import get_email_settings, send_test_email

router = APIRouter()

_MASK = "••••••••••••••••"


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class EmailSettingsIn(BaseModel):
    sender_name: str
    sender_email: EmailStr
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str = ""   # plain text in request — encrypted before DB write
    use_tls: bool = True
    is_active: bool = True


class EmailSettingsOut(BaseModel):
    id: str
    sender_name: str | None
    sender_email: str | None
    smtp_host: str | None
    smtp_port: int | None
    smtp_user: str | None
    smtp_password: str          # returned masked — never the real value
    use_tls: bool
    is_active: bool


# ── GET current settings ──────────────────────────────────────────────────────

@router.get("", response_model=EmailSettingsOut | None)
async def get_settings(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EmailSettings).where(EmailSettings.branch_id == current_user.branch_id)
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        return None

    return {
        "id": str(cfg.id),
        "sender_name": cfg.sender_name,
        "sender_email": cfg.sender_email,
        "smtp_host": cfg.smtp_host,
        "smtp_port": cfg.smtp_port,
        "smtp_user": cfg.smtp_user,
        "smtp_password": _MASK if cfg.smtp_password else "",
        "use_tls": cfg.use_tls,
        "is_active": cfg.is_active,
    }


# ── SAVE (create or update) settings ──────────────────────────────────────────

@router.put("")
async def save_settings(
    body: EmailSettingsIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "NO_BRANCH",
                    "message": "Your account is not scoped to a branch."},
        )

    result = await db.execute(
        select(EmailSettings).where(EmailSettings.branch_id == current_user.branch_id)
    )
    cfg = result.scalar_one_or_none()

    # Only (re)encrypt when a real new password is provided (not blank, not the mask)
    new_password_provided = bool(body.smtp_password) and body.smtp_password != _MASK

    if cfg:
        cfg.sender_name = body.sender_name
        cfg.sender_email = body.sender_email
        cfg.smtp_host = body.smtp_host
        cfg.smtp_port = body.smtp_port
        cfg.smtp_user = body.smtp_user
        cfg.use_tls = body.use_tls
        cfg.is_active = body.is_active
        if new_password_provided:
            cfg.smtp_password = encrypt(body.smtp_password)
    else:
        cfg = EmailSettings(
            branch_id=current_user.branch_id,
            sender_name=body.sender_name,
            sender_email=body.sender_email,
            smtp_host=body.smtp_host,
            smtp_port=body.smtp_port,
            smtp_user=body.smtp_user,
            smtp_password=encrypt(body.smtp_password) if new_password_provided else "",
            use_tls=body.use_tls,
            is_active=body.is_active,
        )
        db.add(cfg)

    await db.commit()
    return {"message": "Email settings saved successfully"}


# ── TEST — send a test email to the logged-in admin ──────────────────────────

@router.post("/test")
async def test_email_settings(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    cfg = await get_email_settings(str(current_user.branch_id), db)
    if not cfg:
        raise HTTPException(
            status_code=400,
            detail={"code": "EMAIL_NOT_CONFIGURED",
                    "message": "Email settings not configured or not active. "
                               "Please save your settings first."},
        )

    if not current_user.email:
        raise HTTPException(
            status_code=400,
            detail={"code": "NO_ADMIN_EMAIL",
                    "message": "Your admin account does not have an email address set."},
        )

    ok, message = await send_test_email(to_email=current_user.email, cfg=cfg)

    if not ok:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "EMAIL_SEND_FAILED",
                "message": message,
                "hint": (
                    "For Gmail: ensure you are using an App Password, not your "
                    "Gmail login password. Generate one at: myaccount.google.com → "
                    "Security → 2-Step Verification → App passwords"
                ),
            },
        )

    return {"message": message, "sent_to": current_user.email}


# ── TOGGLE — disable/enable without deleting settings ─────────────────────────

@router.patch("/toggle")
async def toggle_email(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EmailSettings).where(EmailSettings.branch_id == current_user.branch_id)
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "No email settings found"},
        )
    cfg.is_active = not cfg.is_active
    await db.commit()
    return {"is_active": cfg.is_active}
