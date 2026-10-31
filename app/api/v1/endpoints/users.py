"""
User endpoints.

GET    /api/v1/users/me           — get own profile
PATCH  /api/v1/users/me           — update own profile
DELETE /api/v1/users/me           — deactivate own account
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.auth import get_current_user
from app.schemas import MessageResponse, UserResponse, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(current_user: dict = Depends(get_current_user)) -> Any:
    return current_user


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update current user profile",
)
async def update_me(
    body: UserUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Any:
    return await user_service.update_user(
        session,
        str(current_user["id"]),
        full_name=body.full_name,
        password=body.password,
    )


@router.delete(
    "/me",
    response_model=MessageResponse,
    summary="Deactivate own account (soft delete)",
)
async def deactivate_me(
    session: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Any:
    await user_service.deactivate_user(session, str(current_user["id"]))
    return {"message": "Account deactivated"}
