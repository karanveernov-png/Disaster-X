"""
User service — async CRUD for users.

All methods are async and accept an AsyncSession.
Business rules (validation, conflict checks) are unchanged from the
original Flask version.
"""

from __future__ import annotations

import re
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.services.base import new_uuid, row_to_dict, utcnow

log = get_logger(__name__)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_PASSWORD_MIN_LEN = 8


def _validate_email(email: str) -> str:
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValidationError("Invalid email address format", field="email")
    return email


def _validate_password(password: str) -> None:
    if len(password) < _PASSWORD_MIN_LEN:
        raise ValidationError(
            f"Password must be at least {_PASSWORD_MIN_LEN} characters", field="password"
        )
    if not any(c.isupper() for c in password):
        raise ValidationError(
            "Password must contain at least one uppercase letter", field="password"
        )
    if not any(c.isdigit() for c in password):
        raise ValidationError(
            "Password must contain at least one digit", field="password"
        )


# ── Public API ────────────────────────────────────────────────────────────────

async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str | None = None,
) -> dict[str, Any]:
    email = _validate_email(email)
    _validate_password(password)

    existing = (
        await session.execute(
            sa.text("SELECT id FROM users WHERE email = :email"), {"email": email}
        )
    ).fetchone()
    if existing:
        raise ConflictError("An account with this email already exists")

    user_id = new_uuid()
    now = utcnow()
    hashed = hash_password(password)

    await session.execute(
        sa.text(
            """
            INSERT INTO users (id, email, hashed_password, full_name, created_at, updated_at)
            VALUES (:id, :email, :hashed_password, :full_name, :created_at, :updated_at)
            """
        ),
        {
            "id": user_id,
            "email": email,
            "hashed_password": hashed,
            "full_name": full_name,
            "created_at": now,
            "updated_at": now,
        },
    )

    log.info("User registered: %s", user_id)
    result = await get_user_by_id(session, user_id)
    return result  # type: ignore[return-value]


async def authenticate_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> dict[str, Any]:
    email = email.strip().lower()
    row = (
        await session.execute(
            sa.text("SELECT * FROM users WHERE email = :email"), {"email": email}
        )
    ).fetchone()

    # Constant-time path — always run verify even if user not found
    dummy_hash = "$2b$12$dummydummydummydummydummydummydummydummydummydumm"
    candidate_hash = row_to_dict(row)["hashed_password"] if row else dummy_hash

    if not verify_password(password, candidate_hash) or not row:
        raise AuthenticationError("Incorrect email or password")

    user = row_to_dict(row)
    if not user["is_active"]:
        raise AuthenticationError("Incorrect email or password")

    log.info("User authenticated: %s", user["id"])
    return user


async def get_user_by_id(
    session: AsyncSession,
    user_id: str,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            sa.text("SELECT * FROM users WHERE id = :id"), {"id": str(user_id)}
        )
    ).fetchone()
    return row_to_dict(row)


async def get_user_by_id_or_404(
    session: AsyncSession,
    user_id: str,
) -> dict[str, Any]:
    user = await get_user_by_id(session, user_id)
    if not user:
        raise NotFoundError("User", str(user_id))
    return user


async def update_user(
    session: AsyncSession,
    user_id: str,
    *,
    full_name: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    await get_user_by_id_or_404(session, user_id)

    fields: list[str] = []
    params: dict[str, Any] = {}

    if full_name is not None:
        fields.append("full_name = :full_name")
        params["full_name"] = full_name[:255] if full_name else None

    if password is not None:
        _validate_password(password)
        fields.append("hashed_password = :hashed_password")
        params["hashed_password"] = hash_password(password)

    if not fields:
        return await get_user_by_id(session, user_id)  # type: ignore[return-value]

    fields.append("updated_at = :updated_at")
    params["updated_at"] = utcnow()
    params["id"] = str(user_id)

    await session.execute(
        sa.text(f"UPDATE users SET {', '.join(fields)} WHERE id = :id"), params
    )

    log.info("User updated: %s", user_id)
    return await get_user_by_id(session, user_id)  # type: ignore[return-value]


async def deactivate_user(session: AsyncSession, user_id: str) -> None:
    await get_user_by_id_or_404(session, user_id)
    await session.execute(
        sa.text("UPDATE users SET is_active = FALSE, updated_at = :now WHERE id = :id"),
        {"now": utcnow(), "id": str(user_id)},
    )
    log.info("User deactivated: %s", user_id)
