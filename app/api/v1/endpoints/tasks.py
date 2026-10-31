"""
Task endpoints — all scoped under a project.

GET    /api/v1/projects/{project_id}/tasks         — list tasks (filtered, paginated)
POST   /api/v1/projects/{project_id}/tasks         — create task
GET    /api/v1/projects/{project_id}/tasks/{id}    — get task
PATCH  /api/v1/projects/{project_id}/tasks/{id}    — update task
DELETE /api/v1/projects/{project_id}/tasks/{id}    — delete task
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.auth import get_current_user
from app.schemas import MessageResponse, Page, TaskCreate, TaskResponse, TaskUpdate
from app.services import task_service

router = APIRouter(
    prefix="/projects/{project_id}/tasks",
    tags=["tasks"],
)


@router.get(
    "",
    response_model=Page[TaskResponse],
    summary="List tasks in a project",
)
async def list_tasks(
    project_id: UUID,
    status: Optional[str] = Query(None, description="Filter by status"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    assignee_id: Optional[UUID] = Query(None, description="Filter by assignee"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Any:
    return await task_service.list_tasks(
        session,
        str(project_id),
        str(current_user["id"]),
        status=status,
        priority=priority,
        assignee_id=str(assignee_id) if assignee_id else None,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task in a project",
)
async def create_task(
    project_id: UUID,
    body: TaskCreate,
    session: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Any:
    return await task_service.create_task(
        session,
        str(project_id),
        str(current_user["id"]),
        title=body.title,
        description=body.description,
        status=body.status,
        priority=body.priority,
        assignee_id=str(body.assignee_id) if body.assignee_id else None,
    )


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Get a task by ID",
)
async def get_task(
    project_id: UUID,
    task_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Any:
    return await task_service.get_task_by_id_or_404(
        session, str(task_id), str(project_id), str(current_user["id"])
    )


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Partially update a task",
)
async def update_task(
    project_id: UUID,
    task_id: UUID,
    body: TaskUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Any:
    # Distinguish "not sent" from "sent as null" for assignee_id
    from app.services.task_service import _SENTINEL

    assignee_kwarg = _SENTINEL
    if "assignee_id" in body.model_fields_set:
        assignee_kwarg = str(body.assignee_id) if body.assignee_id else None

    return await task_service.update_task(
        session,
        str(task_id),
        str(project_id),
        str(current_user["id"]),
        title=body.title,
        description=body.description,
        status=body.status,
        priority=body.priority,
        assignee_id=assignee_kwarg,
    )


@router.delete(
    "/{task_id}",
    response_model=MessageResponse,
    summary="Delete a task",
)
async def delete_task(
    project_id: UUID,
    task_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Any:
    await task_service.delete_task(
        session, str(task_id), str(project_id), str(current_user["id"])
    )
    return {"message": "Task deleted"}
