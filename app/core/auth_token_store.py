"""
Auth Token Store — uses PostgreSQL instead of Redis.
Handles: refresh tokens, partial 2FA tokens.
"""

import secrets
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

log = logging.getLogger(__name__)

REFRESH_TOKEN_DAYS  = 7
PARTIAL_2FA_MINUTES = 5


async def store_refresh_token(user_id: str, db: AsyncSession) -> str:
    token      = secrets.token_urlsafe(64)
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS)
    await db.execute(text("""
        INSERT INTO auth_tokens (user_id, token, token_type, expires_at)
        VALUES (:user_id, :token, 'refresh', :expires_at)
    """), {"user_id": user_id, "token": token, "expires_at": expires_at})
    await db.commit()
    return token


async def verify_refresh_token(token: str, db: AsyncSession) -> str | None:
    result = await db.execute(text("""
        SELECT user_id::text
        FROM auth_tokens
        WHERE token      = :token
          AND token_type = 'refresh'
          AND expires_at > now()
    """), {"token": token})
    row = result.fetchone()
    return row[0] if row else None


async def revoke_refresh_token(token: str, db: AsyncSession):
    await db.execute(text(
        "DELETE FROM auth_tokens WHERE token = :token AND token_type = 'refresh'"
    ), {"token": token})
    await db.commit()


async def store_partial_2fa_token(user_id: str, db: AsyncSession) -> str:
    token      = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=PARTIAL_2FA_MINUTES)
    await db.execute(text("""
        INSERT INTO auth_tokens (user_id, token, token_type, expires_at)
        VALUES (:user_id, :token, 'partial_2fa', :expires_at)
    """), {"user_id": user_id, "token": token, "expires_at": expires_at})
    await db.commit()
    return token


async def verify_and_consume_partial_2fa_token(token: str, db: AsyncSession) -> str | None:
    result = await db.execute(text("""
        DELETE FROM auth_tokens
        WHERE token      = :token
          AND token_type = 'partial_2fa'
          AND expires_at > now()
        RETURNING user_id::text
    """), {"token": token})
    row = result.fetchone()
    await db.commit()
    return row[0] if row else None


async def revoke_all_tokens_for_user(user_id: str, db: AsyncSession):
    await db.execute(text(
        "DELETE FROM auth_tokens WHERE user_id = :user_id"
    ), {"user_id": user_id})
    await db.commit()
    log.info(f"[auth] revoked all tokens for user={user_id[:8]}")


async def cleanup_expired_tokens(db: AsyncSession):
    await db.execute(text("DELETE FROM auth_tokens WHERE expires_at < now()"))
    await db.commit()
    log.info("[auth] cleaned up expired tokens")
