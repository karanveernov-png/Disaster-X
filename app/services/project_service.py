"""
Project service — async CRUD with owner-scoped access control.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.services.base import new_uuid, paginate, row_to_dict, utcnow

log = get_logger(__name__)


def _assert_owner(project: dict[str, Any], requester_id: str) -> None:
    if str(project["owner_id"]) != str(requester_id):
        raise AuthorizationError("You do not have permission to modify this project")


# ── Public API ────────────────────────────────────────────────────────────────

async def create_project(
    session: AsyncSession,
    *,
    name: str,
    owner_id: str,
    description: str | None = None,
) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise ValidationError("Project name cannot be empty", field="name")
    if len(name) > 255:
        raise ValidationError("Project name must be 255 characters or fewer", field="name")

    project_id = new_uuid()
    now = utcnow()

    await session.execute(
        sa.text(
            """
            INSERT INTO projects (id, name, description, owner_id, created_at, updated_at)
            VALUES (:id, :name, :description, :owner_id, :created_at, :updated_at)
            """
        ),
        {
            "id": project_id,
            "name": name,
            "description": description,
            "owner_id": owner_id,
            "created_at": now,
            "updated_at": now,
        },
    )

    log.info("Project created: %s by user %s", project_id, owner_id)
    return await get_project_by_id_or_404(session, project_id)


async def get_project_by_id(
    session: AsyncSession,
    project_id: str,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            sa.text("SELECT * FROM projects WHERE id = :id"), {"id": str(project_id)}
        )
    ).fetchone()
    return row_to_dict(row)


async def get_project_by_id_or_404(
    session: AsyncSession,
    project_id: str,
) -> dict[str, Any]:
    project = await get_project_by_id(session, project_id)
    if not project:
        raise NotFoundError("Project", str(project_id))
    return project


async def list_projects(
    session: AsyncSession,
    *,
    owner_id: str,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    count_sql = sa.text(
        "SELECT COUNT(*) AS total FROM projects WHERE owner_id = :owner_id"
    )
    query_sql = sa.text(
        """
        SELECT
            p.*,
            COUNT(t.id) AS task_count
        FROM projects p
        LEFT JOIN tasks t ON t.project_id = p.id
        WHERE p.owner_id = :owner_id
        GROUP BY p.id
        ORDER BY p.updated_at DESC
        """
    )
    return await paginate(session, count_sql, query_sql, {"owner_id": str(owner_id)}, page, page_size)


async def update_project(
    session: AsyncSession,
    project_id: str,
    requester_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    project = await get_project_by_id_or_404(session, project_id)
    _assert_owner(project, requester_id)

    fields: list[str] = []
    params: dict[str, Any] = {}

    if name is not None:
        name = name.strip()
        if not name:
            raise ValidationError("Project name cannot be empty", field="name")
        fields.append("name = :name")
        params["name"] = name[:255]

    if description is not None:
        fields.append("description = :description")
        params["description"] = description or None

    if not fields:
        return project

    fields.append("updated_at = :updated_at")
    params["updated_at"] = utcnow()
    params["id"] = str(project_id)

    await session.execute(
        sa.text(f"UPDATE projects SET {', '.join(fields)} WHERE id = :id"), params
    )

    log.info("Project updated: %s", project_id)
    return await get_project_by_id_or_404(session, project_id)


async def delete_project(
    session: AsyncSession,
    project_id: str,
    requester_id: str,
) -> None:
    project = await get_project_by_id_or_404(session, project_id)
    _assert_owner(project, requester_id)

    await session.execute(
        sa.text("DELETE FROM projects WHERE id = :id"), {"id": str(project_id)}
    )
    log.info("Project deleted: %s by user %s", project_id, requester_id)
