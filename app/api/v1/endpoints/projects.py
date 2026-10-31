"""
Project endpoints.

GET    /api/v1/projects           — list own projects (paginated)
POST   /api/v1/projects           — create project
GET    /api/v1/projects/{id}      — get project
PATCH  /api/v1/projects/{id}      — update project
DELETE /api/v1/projects/{id}      — delete project
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.auth import get_current_user
from app.schemas import MessageResponse, Page, ProjectCreate, ProjectResponse, ProjectUpdate
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get(
    "",
    response_model=Page[ProjectResponse],
    summary="List projects owned by the authenticated user",
)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Any:
    return await project_service.list_projects(
        session,
        owner_id=str(current_user["id"]),
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
)
async def create_project(
    body: ProjectCreate,
    session: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Any:
    return await project_service.create_project(
        session,
        name=body.name,
        owner_id=str(current_user["id"]),
        description=body.description,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get a project by ID",
)
async def get_project(
    project_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Any:
    project = await project_service.get_project_by_id_or_404(session, str(project_id))
    # Only owner can view (consistent with original access model)
    from app.core.exceptions import AuthorizationError
    if str(project["owner_id"]) != str(current_user["id"]):
        raise AuthorizationError()
    return project


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update a project",
)
async def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Any:
    return await project_service.update_project(
        session,
        str(project_id),
        str(current_user["id"]),
        name=body.name,
        description=body.description,
    )


@router.delete(
    "/{project_id}",
    response_model=MessageResponse,
    summary="Delete a project and all its tasks",
)
async def delete_project(
    project_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Any:
    await project_service.delete_project(session, str(project_id), str(current_user["id"]))
    return {"message": "Project deleted"}
