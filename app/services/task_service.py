"""
Task service — async CRUD for tasks scoped under projects.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.services.base import new_uuid, paginate, row_to_dict, utcnow
from app.services.project_service import get_project_by_id_or_404

log = get_logger(__name__)

_VALID_STATUSES = {"todo", "in_progress", "in_review", "done"}
_VALID_PRIORITIES = {"low", "medium", "high", "critical"}

_SENTINEL = object()  # distinguishes "not passed" from "passed as None"


async def _assert_project_access(
    session: AsyncSession,
    project_id: str,
    requester_id: str,
) -> dict[str, Any]:
    project = await get_project_by_id_or_404(session, project_id)
    if str(project["owner_id"]) != str(requester_id):
        raise AuthorizationError("You do not have access to this project")
    return project


async def _assert_assignee_exists(session: AsyncSession, assignee_id: str) -> None:
    row = (
        await session.execute(
            sa.text("SELECT id FROM users WHERE id = :id AND is_active = TRUE"),
            {"id": str(assignee_id)},
        )
    ).fetchone()
    if not row:
        raise ValidationError(
            f"Assignee '{assignee_id}' does not exist or is inactive",
            field="assignee_id",
        )


# ── Public API ────────────────────────────────────────────────────────────────

async def create_task(
    session: AsyncSession,
    project_id: str,
    requester_id: str,
    *,
    title: str,
    description: str | None = None,
    status: str = "todo",
    priority: str = "medium",
    assignee_id: str | None = None,
) -> dict[str, Any]:
    await _assert_project_access(session, project_id, requester_id)

    title = title.strip()
    if not title:
        raise ValidationError("Task title cannot be empty", field="title")
    if len(title) > 500:
        raise ValidationError("Task title must be 500 characters or fewer", field="title")
    if status not in _VALID_STATUSES:
        raise ValidationError(f"Invalid status '{status}'", field="status")
    if priority not in _VALID_PRIORITIES:
        raise ValidationError(f"Invalid priority '{priority}'", field="priority")
    if assignee_id:
        await _assert_assignee_exists(session, str(assignee_id))

    task_id = new_uuid()
    now = utcnow()

    await session.execute(
        sa.text(
            """
            INSERT INTO tasks
                (id, title, description, status, priority, project_id, assignee_id, created_at, updated_at)
            VALUES
                (:id, :title, :description, :status, :priority, :project_id, :assignee_id, :created_at, :updated_at)
            """
        ),
        {
            "id": task_id,
            "title": title,
            "description": description,
            "status": status,
            "priority": priority,
            "project_id": str(project_id),
            "assignee_id": str(assignee_id) if assignee_id else None,
            "created_at": now,
            "updated_at": now,
        },
    )

    log.info("Task created: %s in project %s", task_id, project_id)
    return await get_task_by_id_or_404(session, task_id, project_id, requester_id)


async def get_task_by_id(
    session: AsyncSession,
    task_id: str,
    project_id: str,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            sa.text(
                "SELECT * FROM tasks WHERE id = :id AND project_id = :project_id"
            ),
            {"id": str(task_id), "project_id": str(project_id)},
        )
    ).fetchone()
    return row_to_dict(row)


async def get_task_by_id_or_404(
    session: AsyncSession,
    task_id: str,
    project_id: str,
    requester_id: str,
) -> dict[str, Any]:
    await _assert_project_access(session, project_id, requester_id)
    task = await get_task_by_id(session, task_id, project_id)
    if not task:
        raise NotFoundError("Task", str(task_id))
    return task


async def list_tasks(
    session: AsyncSession,
    project_id: str,
    requester_id: str,
    *,
    status: str | None = None,
    priority: str | None = None,
    assignee_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    await _assert_project_access(session, project_id, requester_id)

    where_clauses = ["project_id = :project_id"]
    params: dict[str, Any] = {"project_id": str(project_id)}

    if status is not None:
        if status not in _VALID_STATUSES:
            raise ValidationError(f"Invalid status filter '{status}'", field="status")
        where_clauses.append("status = :status")
        params["status"] = status

    if priority is not None:
        if priority not in _VALID_PRIORITIES:
            raise ValidationError(f"Invalid priority filter '{priority}'", field="priority")
        where_clauses.append("priority = :priority")
        params["priority"] = priority

    if assignee_id is not None:
        where_clauses.append("assignee_id = :assignee_id")
        params["assignee_id"] = str(assignee_id)

    where = " AND ".join(where_clauses)
    count_sql = sa.text(f"SELECT COUNT(*) AS total FROM tasks WHERE {where}")
    query_sql = sa.text(f"SELECT * FROM tasks WHERE {where} ORDER BY created_at DESC")

    return await paginate(session, count_sql, query_sql, params, page, page_size)


async def update_task(
    session: AsyncSession,
    task_id: str,
    project_id: str,
    requester_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    assignee_id: Any = _SENTINEL,
) -> dict[str, Any]:
    """
    Partial update. Pass ``assignee_id=None`` to clear it;
    omit ``assignee_id`` entirely to leave it unchanged.
    """
    await _assert_project_access(session, project_id, requester_id)
    task = await get_task_by_id(session, task_id, project_id)
    if not task:
        raise NotFoundError("Task", str(task_id))

    fields: list[str] = []
    params: dict[str, Any] = {}

    if title is not None:
        title = title.strip()
        if not title:
            raise ValidationError("Task title cannot be empty", field="title")
        fields.append("title = :title")
        params["title"] = title[:500]

    if description is not None:
        fields.append("description = :description")
        params["description"] = description or None

    if status is not None:
        if status not in _VALID_STATUSES:
            raise ValidationError(f"Invalid status '{status}'", field="status")
        fields.append("status = :status")
        params["status"] = status

    if priority is not None:
        if priority not in _VALID_PRIORITIES:
            raise ValidationError(f"Invalid priority '{priority}'", field="priority")
        fields.append("priority = :priority")
        params["priority"] = priority

    if assignee_id is not _SENTINEL:
        if assignee_id is not None:
            await _assert_assignee_exists(session, str(assignee_id))
        fields.append("assignee_id = :assignee_id")
        params["assignee_id"] = str(assignee_id) if assignee_id else None

    if not fields:
        return task

    fields.append("updated_at = :updated_at")
    params["updated_at"] = utcnow()
    params["id"] = str(task_id)

    await session.execute(
        sa.text(f"UPDATE tasks SET {', '.join(fields)} WHERE id = :id"), params
    )
    log.info("Task updated: %s", task_id)
    return await get_task_by_id(session, task_id, project_id)  # type: ignore[return-value]


async def delete_task(
    session: AsyncSession,
    task_id: str,
    project_id: str,
    requester_id: str,
) -> None:
    await _assert_project_access(session, project_id, requester_id)
    task = await get_task_by_id(session, task_id, project_id)
    if not task:
        raise NotFoundError("Task", str(task_id))

    await session.execute(
        sa.text("DELETE FROM tasks WHERE id = :id"), {"id": str(task_id)}
    )
    log.info("Task deleted: %s from project %s", task_id, project_id)
