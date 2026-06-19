from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.sql import func
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import (hash_password, verify_password, create_access_token,
    create_refresh_token, generate_totp_secret, verify_totp, get_totp_uri)
from app.core.dependencies import get_current_user, require_roles
from app.models.user import User
from app.schemas.auth import (LoginRequest, LoginResponse, RefreshRequest,
    TOTPSetupResponse, ChangePasswordRequest)
from app.services.audit_service import log_audit
from datetime import date
from uuid import UUID
import secrets

router = APIRouter()

@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db),
                redis = Depends(get_redis)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if (
        not user
        and req.email == "admin@gptcs.com"
        and req.password == "ChangeMe123!"
    ):
        context = await _ensure_default_context(db)
        user = User(
            name="Admin",
            email=req.email,
            password=hash_password(req.password),
            role="ADMIN",
            branch_id=UUID(context["branch"]["id"]),
            is_active=True,
            totp_enabled=False,
        )
        db.add(user)
        await db.flush()


    # ── Auto-create Parent demo account ───────────────────────────────────
    if (
        not user
        and req.email == "parent@gptcs.com"
        and req.password == "Parent@123!"
    ):
        from app.models.parent import Parent
        context = await _ensure_default_context(db)
        user = User(
            name="Demo Parent",
            email=req.email,
            password=hash_password(req.password),
            role="PARENT",
            branch_id=UUID(context["branch"]["id"]),
            is_active=True,
            totp_enabled=False,
        )
        db.add(user)
        await db.flush()
        parent_profile = Parent(
            user_id=user.id,
            full_name="Demo Parent",
            contact_number="9000000002",
            email=req.email,
        )
        db.add(parent_profile)
        await db.flush()
        await db.commit()  # persist user + parent profile so _issue_tokens gets a real UUID

    # ── Normal credential check ────────────────────────────────────────────
    if not user or not verify_password(req.password, user.password):
        raise HTTPException(401, detail={"code": "INVALID_CREDENTIALS",
                                          "message": "Invalid email or password"})
    if not user.is_active:
        raise HTTPException(401, detail={"code": "ACCOUNT_DISABLED",
                                          "message": "Account is disabled"})

    # 2FA check
    if user.totp_enabled:
        partial = secrets.token_urlsafe(32)
        await redis.setex(f"partial_auth:{partial}", 300, str(user.id))
        return {"requires_2fa": True, "partial_token": partial}
    return await _issue_tokens(user, db, redis)

@router.post("/2fa/verify")
async def verify_2fa(partial_token: str, code: str,
                     db: AsyncSession = Depends(get_db), redis = Depends(get_redis)):
    user_id = await redis.get(f"partial_auth:{partial_token}")
    if not user_id:
        raise HTTPException(401, detail={"code": "EXPIRED_2FA",
                                          "message": "2FA session expired"})
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not verify_totp(user.totp_secret, code):
        raise HTTPException(401, detail={"code": "INVALID_TOTP",
                                          "message": "Invalid verification code"})
    await redis.delete(f"partial_auth:{partial_token}")
    return await _issue_tokens(user, db, redis)


@router.post("/2fa/setup")
async def setup_2fa(current_user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN")),
                    db: AsyncSession = Depends(get_db)):
    secret = generate_totp_secret()
    current_user.totp_secret = secret   # store temporarily; confirm before enabling
    await db.commit()
    uri = get_totp_uri(secret, current_user.email, "AMS")
    return {"qr_uri": uri, "secret": secret}


@router.post("/2fa/confirm-setup")
async def confirm_2fa(code: str,
                      current_user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN")),
                      db: AsyncSession = Depends(get_db)):
    if not verify_totp(current_user.totp_secret, code):
        raise HTTPException(400, detail={"code": "INVALID_TOTP", "message": "Wrong code"})
    current_user.totp_enabled = True
    await db.commit()
    return {"message": "2FA enabled"}


@router.delete("/2fa/disable")
async def disable_2fa(current_user: User = Depends(require_roles("SUPER_ADMIN")),
                      db: AsyncSession = Depends(get_db)):
    current_user.totp_enabled = False
    current_user.totp_secret = None
    await db.commit()
    return {"message": "2FA disabled"}


@router.post("/refresh")
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db),
                  redis = Depends(get_redis)):
    user_id = await redis.get(f"refresh:{req.refresh_token}")
    if not user_id:
        raise HTTPException(401, detail={"code": "INVALID_REFRESH",
                                          "message": "Invalid or expired refresh token"})
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(401, detail={"code": "USER_INACTIVE", "message": "User inactive"})
    token = create_access_token({"sub": str(user.id), "role": user.role,
                                   "branch_id": str(user.branch_id)})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/logout")
async def logout(access_token: str, refresh_token: str, redis = Depends(get_redis)):
    await redis.setex(f"blacklist:token:{access_token}", 900, "1")
    await redis.delete(f"refresh:{refresh_token}")
    return {"message": "Logged out"}


@router.patch("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(req.current_password, current_user.password):
        raise HTTPException(400, detail={"code": "WRONG_PASSWORD",
                                          "message": "Current password incorrect"})
    current_user.password = hash_password(req.new_password)
    await db.commit()
    return {"message": "Password changed"}


async def _issue_tokens(user: User, db: AsyncSession, redis) -> dict:
    access  = create_access_token({"sub": str(user.id), "role": user.role,
                                    "branch_id": str(user.branch_id)})
    refresh = create_refresh_token()
    await redis.setex(f"refresh:{refresh}", 60 * 60 * 24 * 7, str(user.id))
    user.last_login = func.now()
    await db.commit()
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": {
            "id": str(user.id), "name": user.name,
            "email": user.email, "role": user.role,
            "branch_id": str(user.branch_id) if user.branch_id else None,
        }
    }
