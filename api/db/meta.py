"""Metadata repository: datasets, conversations and messages (schema `app`)."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

SCHEMA_RE = re.compile(r"^ds_[0-9a-f]{12}$")


def new_id() -> str:
    return uuid.uuid4().hex


def new_schema_name() -> str:
    return f"ds_{uuid.uuid4().hex[:12]}"


def _quote_schema(schema_name: str) -> str:
    if not SCHEMA_RE.match(schema_name):
        raise ValueError("invalid dataset schema name")
    return f'"{schema_name}"'


# ---------------------------------------------------------------- datasets


async def drop_schema(conn: asyncpg.Connection, schema_name: str) -> None:
    await conn.execute(f"DROP SCHEMA IF EXISTS {_quote_schema(schema_name)} CASCADE")


async def delete_dataset(pool: asyncpg.Pool, visitor_id: str) -> bool:
    """Drop the visitor's dataset schema and metadata (conversations cascade)."""
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "DELETE FROM app.datasets WHERE visitor_id = $1 RETURNING schema_name", visitor_id
        )
        if row is None:
            return False
        await drop_schema(conn, row["schema_name"])
        return True


async def get_active_dataset(pool: asyncpg.Pool, visitor_id: str) -> dict[str, Any] | None:
    row = await pool.fetchrow("SELECT * FROM app.datasets WHERE visitor_id = $1", visitor_id)
    if row is None:
        return None
    if row["expires_at"] <= datetime.now(UTC):
        await delete_dataset(pool, visitor_id)
        return None
    return dict(row)


async def insert_dataset(
    conn: asyncpg.Connection,
    *,
    visitor_id: str,
    schema_name: str,
    name: str,
    tables: list[dict[str, Any]],
    ttl_hours: int,
) -> dict[str, Any]:
    """Replace the visitor's dataset row. Must run inside the commit transaction."""
    old = await conn.fetchrow(
        "DELETE FROM app.datasets WHERE visitor_id = $1 RETURNING schema_name", visitor_id
    )
    if old is not None:
        await drop_schema(conn, old["schema_name"])
    dataset_id = new_id()
    expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)
    row = await conn.fetchrow(
        """
        INSERT INTO app.datasets (id, visitor_id, schema_name, name, tables, expires_at)
        VALUES ($1, $2, $3, $4, $5, $6) RETURNING *
        """,
        dataset_id,
        visitor_id,
        schema_name,
        name,
        tables,
        expires_at,
    )
    return dict(row)


async def count_active_datasets(pool: asyncpg.Pool, exclude_visitor_id: str) -> int:
    return await pool.fetchval(
        "SELECT count(*) FROM app.datasets WHERE visitor_id <> $1 AND expires_at > now()",
        exclude_visitor_id,
    )


async def sweep_expired(pool: asyncpg.Pool) -> int:
    rows = await pool.fetch("SELECT visitor_id FROM app.datasets WHERE expires_at <= now()")
    for row in rows:
        await delete_dataset(pool, row["visitor_id"])
    return len(rows)


# ----------------------------------------------------------- conversations


async def create_conversation(pool: asyncpg.Pool, dataset_id: str) -> str:
    conv_id = new_id()
    await pool.execute(
        "INSERT INTO app.conversations (id, dataset_id) VALUES ($1, $2)", conv_id, dataset_id
    )
    return conv_id


async def get_conversation(
    pool: asyncpg.Pool, conversation_id: str, dataset_id: str
) -> dict[str, Any] | None:
    row = await pool.fetchrow(
        "SELECT * FROM app.conversations WHERE id = $1 AND dataset_id = $2",
        conversation_id,
        dataset_id,
    )
    return dict(row) if row else None


async def list_conversations(pool: asyncpg.Pool, dataset_id: str) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        "SELECT id, title, created_at, updated_at FROM app.conversations "
        "WHERE dataset_id = $1 ORDER BY updated_at DESC LIMIT 50",
        dataset_id,
    )
    return [dict(r) for r in rows]


async def set_conversation_title(pool: asyncpg.Pool, conversation_id: str, title: str) -> None:
    await pool.execute(
        "UPDATE app.conversations SET title = $2, updated_at = now() WHERE id = $1",
        conversation_id,
        title,
    )


async def touch_conversation(pool: asyncpg.Pool, conversation_id: str) -> None:
    await pool.execute(
        "UPDATE app.conversations SET updated_at = now() WHERE id = $1", conversation_id
    )


async def delete_conversation(pool: asyncpg.Pool, conversation_id: str, dataset_id: str) -> None:
    await pool.execute(
        "DELETE FROM app.conversations WHERE id = $1 AND dataset_id = $2",
        conversation_id,
        dataset_id,
    )


# ---------------------------------------------------------------- messages


async def insert_message(
    pool: asyncpg.Pool, conversation_id: str, role: str, content: str, status: str
) -> str:
    message_id = new_id()
    await pool.execute(
        "INSERT INTO app.messages (id, conversation_id, role, content, status) "
        "VALUES ($1, $2, $3, $4, $5)",
        message_id,
        conversation_id,
        role,
        content,
        status,
    )
    return message_id


async def finalize_message(
    pool: asyncpg.Pool,
    message_id: str,
    *,
    content: str,
    sql: Any,
    tables: Any,
    chart: Any,
    status: str,
) -> None:
    await pool.execute(
        "UPDATE app.messages SET content = $2, sql = $3, tables = $4, chart = $5, status = $6 "
        "WHERE id = $1",
        message_id,
        content,
        sql,
        tables,
        chart,
        status,
    )


async def list_messages(pool: asyncpg.Pool, conversation_id: str) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        "SELECT id, role, content, sql, tables, chart, status, created_at FROM app.messages "
        "WHERE conversation_id = $1 ORDER BY created_at, id",
        conversation_id,
    )
    return [dict(r) for r in rows]


async def recent_history(
    pool: asyncpg.Pool, conversation_id: str, limit: int = 6
) -> list[dict[str, Any]]:
    """Last completed messages (oldest first) for the condense step."""
    rows = await pool.fetch(
        "SELECT role, content FROM app.messages "
        "WHERE conversation_id = $1 AND status = 'completed' "
        "ORDER BY created_at DESC, id DESC LIMIT $2",
        conversation_id,
        limit,
    )
    return [dict(r) for r in reversed(rows)]
