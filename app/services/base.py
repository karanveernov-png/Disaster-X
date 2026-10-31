"""
Base service utilities for async SQLAlchemy.

Mirrors the original sqlite3-based helpers but works with asyncpg
and SQLAlchemy Core text() queries.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


def row_to_dict(row: Any) -> dict[str, Any] | None:
    """Convert a SQLAlchemy Row (or Mapping) to a plain dict."""
    if row is None:
        return None
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row)


def rows_to_list(rows: list[Any]) -> list[dict[str, Any]]:
    return [row_to_dict(r) for r in rows if r is not None]  # type: ignore[misc]


async def paginate(
    session: AsyncSession,
    count_sql: sa.TextClause,
    query_sql: sa.TextClause,
    params: dict[str, Any],
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """
    Async paginate helper.

    count_sql must select a single column named `total`.
    query_sql must NOT include LIMIT/OFFSET — they are appended here.

    Returns the standard envelope::

        {
            "items": [...],
            "total": 42,
            "page": 1,
            "page_size": 20,
            "pages": 3,
        }
    """
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    offset = (page - 1) * page_size

    total_row = (await session.execute(count_sql, params)).fetchone()
    total = total_row[0] if total_row else 0

    paginated_sql = sa.text(str(query_sql.text) + " LIMIT :limit OFFSET :offset")
    rows = (
        await session.execute(paginated_sql, {**params, "limit": page_size, "offset": offset})
    ).fetchall()

    return {
        "items": rows_to_list(rows),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, math.ceil(total / page_size)),
    }
