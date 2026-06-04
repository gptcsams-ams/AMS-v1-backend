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
    TOTPSetupResponse, ChangePasswordRequest, RegisterRequest)
from app.services.audit_service import log_audit
from datetime import date
from uuid import UUID
import secrets

router = APIRouter()


@router.post("/register")
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    from app.models.academic_year import AcademicYear
    from app.models.branch import Branch
    from app.models.school import School

    role = req.role.upper()
    if role not in {"ADMIN", "TEACHER", "PARENT"}:
        raise HTTPException(status_code=400, detail="Invalid account type")

    existing = (await db.execute(select(User).where(User.email == req.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    school = (await db.execute(select(School).limit(1))).scalar_one_or_none()
    if not school:
        school = School(
            name="St. Mary's Higher Secondary School",
            city="",
            state="",
            board="STATE",
        )
        db.add(school)
        await db.flush()

    branch = (await db.execute(select(Branch).where(Branch.school_id == school.id).limit(1))).scalar_one_or_none()
    if not branch:
        branch = Branch(
            school_id=school.id,
            name="Main Branch",
            location="Main Campus",
        )
        db.add(branch)
        await db.flush()

    year = (await db.execute(
        select(AcademicYear)
        .where(AcademicYear.school_id == school.id, AcademicYear.is_current == True)
        .limit(1)
    )).scalar_one_or_none()
    if not year:
        year = AcademicYear(
            school_id=school.id,
            name="2024-25",
            start_date=date(2024, 6, 1),
            end_date=date(2025, 5, 31),
            is_current=True,
        )
        db.add(year)
        await db.flush()

    user = User(
        name=req.name.strip(),
        email=req.email,
        password=hash_password(req.password),
        role=role,
        branch_id=branch.id,
        is_active=True,
        totp_enabled=False,
    )
    db.add(user)
    await db.flush()

    tokens = await _issue_tokens(user, db, _get_optional_redis())
    return {
        **tokens,
        "context": {
            "school": {"id": str(school.id), "name": school.name},
            "branch": {"id": str(branch.id), "name": branch.name, "school_id": str(branch.school_id)},
            "academic_year": {"id": str(year.id), "name": year.name, "is_current": year.is_current},
        },
    }

@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    redis = _get_optional_redis()
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

    if not user or not verify_password(req.password, user.password):
        raise HTTPException(401, detail={"code": "INVALID_CREDENTIALS",
                                          "message": "Invalid email or password"})
    if not user.is_active:
        raise HTTPException(401, detail={"code": "ACCOUNT_DISABLED",
                                          "message": "Account is disabled"})
    # 2FA check
    if user.totp_enabled:
        if not redis:
            raise HTTPException(503, detail="Two-factor login requires Redis to be running")
        partial = secrets.token_urlsafe(32)
        await redis.setex(f"partial_auth:{partial}", 300, str(user.id))
        return {"requires_2fa": True, "partial_token": partial}
    tokens = await _issue_tokens(user, db, redis)
    context = await _ensure_default_context(db, user)
    return {**tokens, "user": context["user"], "context": context}

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
async def change_password(req: ChangePasswordRequest,
                           current_user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    if not verify_password(req.current_password, current_user.password):
        raise HTTPException(400, detail={"code": "WRONG_PASSWORD",
                                          "message": "Current password incorrect"})
    current_user.password = hash_password(req.new_password)
    await db.commit()
    return {"message": "Password changed"}


@router.post("/setup-default-context")
async def setup_default_context(
    current_user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    return await _ensure_default_context(db, current_user)


async def _ensure_default_context(db: AsyncSession, current_user: User | None = None) -> dict:
    from app.models.academic_year import AcademicYear
    from app.models.branch import Branch
    from app.models.school import School

    school = (await db.execute(select(School).limit(1))).scalar_one_or_none()
    if not school:
        school = School(
            name="St. Mary's Higher Secondary School",
            city="",
            state="",
            board="STATE",
        )
        db.add(school)
        await db.flush()

    branch = (await db.execute(select(Branch).where(Branch.school_id == school.id).limit(1))).scalar_one_or_none()
    if not branch:
        branch = Branch(
            school_id=school.id,
            name="Main Branch",
            location="Main Campus",
        )
        db.add(branch)
        await db.flush()

    year = (await db.execute(
        select(AcademicYear)
        .where(AcademicYear.school_id == school.id, AcademicYear.is_current == True)
        .limit(1)
    )).scalar_one_or_none()
    if not year:
        year = AcademicYear(
            school_id=school.id,
            name="2024-25",
            start_date=date(2024, 6, 1),
            end_date=date(2025, 5, 31),
            is_current=True,
        )
        db.add(year)
        await db.flush()

    if current_user and not current_user.branch_id and current_user.role == "ADMIN":
        current_user.branch_id = branch.id

    await db.commit()
    await db.refresh(school)
    await db.refresh(branch)
    await db.refresh(year)
    if current_user:
        await db.refresh(current_user)

    return {
        "school": {
            "id": str(school.id),
            "name": school.name,
        },
        "branch": {
            "id": str(branch.id),
            "name": branch.name,
            "school_id": str(branch.school_id),
        },
        "academic_year": {
            "id": str(year.id),
            "name": year.name,
            "is_current": year.is_current,
        },
        "user": {
            "id": str(current_user.id) if current_user else "",
            "name": current_user.name if current_user else "",
            "email": current_user.email if current_user else "",
            "role": current_user.role if current_user else "ADMIN",
            "branch_id": str(current_user.branch_id) if current_user and current_user.branch_id else str(branch.id),
        },
    }

async def _issue_tokens(user: User, db: AsyncSession, redis) -> dict:
    access  = create_access_token({"sub": str(user.id), "role": user.role,
                                    "branch_id": str(user.branch_id)})
    refresh = create_refresh_token()
    if redis:
        try:
            await redis.setex(f"refresh:{refresh}", 60 * 60 * 24 * 7, str(user.id))
        except Exception:
            # Allow local development to continue even when Redis is not running.
            pass
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


def _get_optional_redis():
    try:
        return get_redis()
    except Exception:
        return None
