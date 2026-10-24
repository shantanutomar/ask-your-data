"""Draft datasets: parsed + typed data held in Redis until the user confirms."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel
from redis.asyncio import Redis

from config import Settings
from ingest.parsers import IngestError, RawTable
from ingest.types import ColumnType, canonical, infer_type, sanitize_identifier

DRAFT_TTL_SECONDS = 30 * 60
PREVIEW_ROWS = 5


class DraftColumn(BaseModel):
    name: str
    type: ColumnType


class DraftTable(BaseModel):
    name: str
    columns: list[DraftColumn]
    rows: list[list[Any]]


class Draft(BaseModel):
    visitor_id: str
    name: str
    tables: list[DraftTable]


def build_draft(
    raw_tables: list[RawTable], *, visitor_id: str, dataset_name: str, settings: Settings
) -> Draft:
    if not raw_tables:
        raise IngestError("No tables were found in the data.")
    if len(raw_tables) > settings.max_tables:
        raise IngestError(
            f"Too many tables ({len(raw_tables)}); the limit is {settings.max_tables}."
        )
    total_rows = sum(len(t.rows) for t in raw_tables)
    if total_rows > settings.max_total_rows:
        raise IngestError(f"Too many rows ({total_rows}); the limit is {settings.max_total_rows}.")

    table_names: set[str] = set()
    tables: list[DraftTable] = []
    for raw in raw_tables:
        if not raw.columns:
            raise IngestError(f"Table '{raw.name}' has no columns.")
        if len(raw.columns) > settings.max_columns_per_table:
            raise IngestError(
                f"Table '{raw.name}' has {len(raw.columns)} columns; "
                f"the limit is {settings.max_columns_per_table}."
            )
        if not raw.rows:
            raise IngestError(f"Table '{raw.name}' has no rows.")
        col_names: set[str] = set()
        columns: list[DraftColumn] = []
        width = len(raw.columns)
        norm_rows = [(list(r) + [None] * width)[:width] for r in raw.rows]
        for idx, raw_col in enumerate(raw.columns):
            name = sanitize_identifier(raw_col, col_names, fallback=f"column_{idx + 1}")
            ctype = infer_type([r[idx] for r in norm_rows])
            columns.append(DraftColumn(name=name, type=ctype))
        rows = [[canonical(v, columns[i].type) for i, v in enumerate(r)] for r in norm_rows]
        tables.append(
            DraftTable(
                name=sanitize_identifier(raw.name, table_names, fallback="data"),
                columns=columns,
                rows=rows,
            )
        )
    return Draft(visitor_id=visitor_id, name=dataset_name[:80] or "My data", tables=tables)


def draft_preview(draft_id: str, draft: Draft) -> dict[str, Any]:
    return {
        "draft_id": draft_id,
        "name": draft.name,
        "tables": [
            {
                "name": t.name,
                "row_count": len(t.rows),
                "columns": [c.model_dump() for c in t.columns],
                "sample_rows": t.rows[:PREVIEW_ROWS],
            }
            for t in draft.tables
        ],
    }


def _key(namespace: str, draft_id: str) -> str:
    return f"{namespace}:draft:{draft_id}"


async def save_draft(redis: Redis, namespace: str, draft: Draft) -> str:
    draft_id = uuid.uuid4().hex
    await redis.set(_key(namespace, draft_id), draft.model_dump_json(), ex=DRAFT_TTL_SECONDS)
    return draft_id


async def load_draft(redis: Redis, namespace: str, draft_id: str, visitor_id: str) -> Draft:
    raw = await redis.get(_key(namespace, draft_id))
    if raw is None:
        raise IngestError("This preview has expired. Please upload your data again.")
    draft = Draft.model_validate_json(raw)
    if draft.visitor_id != visitor_id:
        raise IngestError("This preview has expired. Please upload your data again.")
    return draft


async def delete_draft(redis: Redis, namespace: str, draft_id: str) -> None:
    await redis.delete(_key(namespace, draft_id))
