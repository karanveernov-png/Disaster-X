"""
Auth service — async token lifecycle management.

Login → issue token pair
Refresh → validate, check blocklist, rotate tokens
Logout → revoke JTI
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.logging import get_logger
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)
from app.services.base import utcnow
from app.services.user_service import authenticate_user, get_user_by_id

log = get_logger(__name__)


# ── Token pair helpers ────────────────────────────────────────────────────────

def _issue_tokens(user: dict[str, Any]) -> dict[str, str]:
    user_id = str(user["id"])
    access = create_access_token(
        user_id, extra={"is_superuser": bool(user.get("is_superuser"))}
    )
    refresh = create_refresh_token(user_id)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


# ── Blocklist helpers ─────────────────────────────────────────────────────────

async def _is_jti_revoked(session: AsyncSession, jti: str) -> bool:
    row = (
        await session.execute(
            sa.text("SELECT jti FROM token_blocklist WHERE jti = :jti"), {"jti": jti}
        )
    ).fetchone()
    return row is not None


async def _revoke_jti(session: AsyncSession, jti: str, user_id: str) -> None:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    await session.execute(
        sa.text(
            """
            INSERT INTO token_blocklist (jti, user_id, expires_at)
            VALUES (:jti, :user_id, :expires_at)
            ON CONFLICT (jti) DO NOTHING
            """
        ),
        {"jti": jti, "user_id": user_id, "expires_at": expires_at},
    )
    log.info("Refresh token revoked: jti=%s user=%s", jti, user_id)


async def sweep_expired_blocklist_entries(session: AsyncSession) -> int:
    """Remove expired token blocklist entries. Call periodically."""
    result = await session.execute(
        sa.text("DELETE FROM token_blocklist WHERE expires_at <= :now"), {"now": utcnow()}
    )
    return result.rowcount  # type: ignore[return-value]


# ── Public API ────────────────────────────────────────────────────────────────

async def login(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> dict[str, str]:
    user = await authenticate_user(session, email=email, password=password)
    tokens = _issue_tokens(user)
    log.info("User logged in: %s", user["id"])
    return tokens


async def refresh_tokens(
    session: AsyncSession,
    *,
    refresh_token: str,
) -> dict[str, str]:
    try:
        payload = decode_refresh_token(refresh_token)
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc

    jti: str = payload.get("jti", "")
    user_id: str = payload["sub"]

    if await _is_jti_revoked(session, jti):
        raise AuthenticationError("Refresh token has been revoked")

    user = await get_user_by_id(session, user_id)
    if not user or not user.get("is_active"):
        raise AuthenticationError("User not found or inactive")

    # Rotate — invalidate the old JTI immediately
    await _revoke_jti(session, jti, user_id)

    tokens = _issue_tokens(user)
    log.info("Tokens refreshed for user: %s", user_id)
    return tokens


async def logout(
    session: AsyncSession,
    *,
    refresh_token: str,
    user_id: str,
) -> None:
    try:
        payload = decode_refresh_token(refresh_token)
        jti: str = payload.get("jti", "")
        if jti and str(payload["sub"]) == str(user_id):
            await _revoke_jti(session, jti, user_id)
    except TokenError:
        pass  # already invalid — idempotent


async def get_current_user_from_token(
    session: AsyncSession,
    *,
    access_token: str,
) -> dict[str, Any]:
    try:
        payload = decode_access_token(access_token)
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc

    user_id: str = payload["sub"]
    user = await get_user_by_id(session, user_id)
    if not user:
        raise AuthenticationError("User not found")
    if not user.get("is_active"):
        raise AuthenticationError("Account is deactivated")
    return user
