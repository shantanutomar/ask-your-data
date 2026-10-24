"""Run validated SELECTs in a read-only transaction as the `ayd_reader` role."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import asyncpg

from sql.validator import SqlValidationError, validate_select
from utils import to_jsonable

_SCHEMA_RE = re.compile(r"^ds_[0-9a-f]{12}$")


class QueryError(Exception):
    """A user-presentable SQL failure (validation or database error). Drives the retry loop."""


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool


async def execute_query(
    pool: asyncpg.Pool,
    *,
    schema_name: str,
    sql: str,
    allowed_tables: set[str],
    max_rows: int,
    timeout_ms: int,
) -> QueryResult:
    if not _SCHEMA_RE.match(schema_name):
        raise QueryError("Invalid dataset.")
    try:
        safe_sql = validate_select(sql, schema_name, allowed_tables)
    except SqlValidationError as exc:
        raise QueryError(str(exc)) from exc

    limited = f"SELECT * FROM ({safe_sql}) AS _q LIMIT {int(max_rows) + 1}"
    try:
        async with pool.acquire() as conn:
            async with conn.transaction(readonly=True):
                await conn.execute("SET LOCAL ROLE ayd_reader")
                await conn.execute(f'SET LOCAL search_path TO "{schema_name}"')
                await conn.execute("SET LOCAL TIME ZONE 'UTC'")
                await conn.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
                stmt = await conn.prepare(limited)
                columns = [a.name for a in stmt.get_attributes()]
                records = await stmt.fetch()
    except asyncpg.QueryCanceledError as exc:
        raise QueryError("The query took too long and was cancelled.") from exc
    except asyncpg.PostgresError as exc:
        message = (exc.message or type(exc).__name__).splitlines()[0]
        raise QueryError(message[:300]) from exc

    truncated = len(records) > max_rows
    rows = [[to_jsonable(v) for v in rec.values()] for rec in records[:max_rows]]
    return QueryResult(columns=columns, rows=rows, truncated=truncated)
