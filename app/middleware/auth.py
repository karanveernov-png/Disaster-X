"""
FastAPI auth dependencies.

`get_current_user` — extracts the Bearer token from Authorization header,
decodes it, loads the user, and injects the user dict into the route.

`get_current_superuser` — same, but raises 403 if not a superuser.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.db.database import get_db
from app.services.auth_service import get_current_user_from_token

_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    FastAPI dependency — resolves the authenticated user from JWT.

    Raises HTTP 401 on invalid / expired token.
    Raises HTTP 401 if the user no longer exists or is deactivated.
    """
    try:
        return await get_current_user_from_token(
            session, access_token=credentials.credentials
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_superuser(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    FastAPI dependency — like `get_current_user` but requires superuser flag.
    Raises HTTP 403 otherwise.
    """
    if not current_user.get("is_superuser"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required",
        )
    return current_user
