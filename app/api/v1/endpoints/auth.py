"""
Auth endpoints: register, login, refresh, logout.

POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/auth/me
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.auth import get_current_user
from app.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from app.services import auth_service, user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(body: UserCreate, session: AsyncSession = Depends(get_db)) -> Any:
    user = await user_service.create_user(
        session,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
    )
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive token pair",
)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db)) -> Any:
    return await auth_service.login(session, email=body.email, password=body.password)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate tokens using a valid refresh token",
)
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_db)) -> Any:
    return await auth_service.refresh_tokens(session, refresh_token=body.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke refresh token",
)
async def logout(
    body: LogoutRequest,
    session: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> None:
    await auth_service.logout(
        session,
        refresh_token=body.refresh_token,
        user_id=str(current_user["id"]),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get authenticated user's profile",
)
async def me(current_user: dict = Depends(get_current_user)) -> Any:
    return current_user
