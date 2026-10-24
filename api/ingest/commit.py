"""Commit a draft: apply the user's edits, create the dataset schema and bulk-load the data."""

from __future__ import annotations

from collections import Counter
from typing import Any

import asyncpg
from pydantic import BaseModel

from config import Settings
from db import meta
from ingest.drafts import Draft
from ingest.parsers import CapacityError, IngestError
from ingest.types import PG_TYPES, CoerceError, ColumnType, coerce, sanitize_identifier
from utils import to_jsonable

MAX_DISTINCT_FOR_CONTEXT = 30
SAMPLE_ROWS = 3


class ColumnEdit(BaseModel):
    source: str
    name: str
    type: ColumnType


class TableEdit(BaseModel):
    source: str
    name: str
    columns: list[ColumnEdit]


class CommitRequest(BaseModel):
    draft_id: str
    dataset_name: str | None = None
    tables: list[TableEdit] | None = None  # omitted tables/columns are dropped


class FinalTable(BaseModel):
    name: str
    columns: list[tuple[str, ColumnType]]
    rows: list[tuple[Any, ...]]


def apply_edits(
    draft: Draft, edits: list[TableEdit] | None, settings: Settings
) -> list[FinalTable]:
    by_name = {t.name: t for t in draft.tables}
    if edits is None:
        edits = [
            TableEdit(
                source=t.name,
                name=t.name,
                columns=[ColumnEdit(source=c.name, name=c.name, type=c.type) for c in t.columns],
            )
            for t in draft.tables
        ]
    if not edits:
        raise IngestError("Keep at least one table.")
    if len(edits) > settings.max_tables:
        raise IngestError(f"Too many tables; the limit is {settings.max_tables}.")

    taken_tables: set[str] = set()
    result: list[FinalTable] = []
    for edit in edits:
        src = by_name.get(edit.source)
        if src is None:
            raise IngestError(f"Unknown table '{edit.source}'.")
        if not edit.columns:
            raise IngestError(f"Table '{edit.name}' needs at least one column.")
        if len(edit.columns) > settings.max_columns_per_table:
            raise IngestError(f"Table '{edit.name}' has too many columns.")
        index = {c.name: i for i, c in enumerate(src.columns)}
        taken_cols: set[str] = set()
        cols: list[tuple[str, ColumnType]] = []
        picks: list[int] = []
        for ce in edit.columns:
            if ce.source not in index:
                raise IngestError(f"Unknown column '{ce.source}' in '{edit.source}'.")
            cols.append((sanitize_identifier(ce.name, taken_cols), ce.type))
            picks.append(index[ce.source])
        rows: list[tuple[Any, ...]] = []
        for row in src.rows:
            out = []
            for pos, src_idx in enumerate(picks):
                try:
                    out.append(coerce(row[src_idx], cols[pos][1]))
                except CoerceError as exc:
                    raise IngestError(
                        f'Column "{cols[pos][0]}" in "{edit.name}" cannot be {cols[pos][1]}: '
                        f'"{row[src_idx]}" ({exc}). Choose "text" or drop the column.'
                    ) from exc
            rows.append(tuple(out))
        result.append(
            FinalTable(
                name=sanitize_identifier(edit.name, taken_tables, "data"), columns=cols, rows=rows
            )
        )
    return result


def build_table_context(table: FinalTable) -> dict[str, Any]:
    """Per-table summary stored on the dataset: columns, row count, samples, value hints."""
    columns: list[dict[str, Any]] = []
    for idx, (name, ctype) in enumerate(table.columns):
        entry: dict[str, Any] = {"name": name, "type": ctype}
        values = [r[idx] for r in table.rows if r[idx] is not None]
        if ctype == "text" and values:
            counts = Counter(values)
            if len(counts) <= MAX_DISTINCT_FOR_CONTEXT:
                entry["distinct"] = [v for v, _ in counts.most_common()]
        elif ctype in ("integer", "numeric", "date", "timestamp") and values:
            entry["min"] = to_jsonable(min(values))
            entry["max"] = to_jsonable(max(values))
        columns.append(entry)
    samples = [
        {name: to_jsonable(v) for (name, _), v in zip(table.columns, row, strict=True)}
        for row in table.rows[:SAMPLE_ROWS]
    ]
    return {
        "name": table.name,
        "row_count": len(table.rows),
        "columns": columns,
        "samples": samples,
    }


async def create_dataset(
    pool: asyncpg.Pool,
    *,
    visitor_id: str,
    dataset_name: str,
    tables: list[FinalTable],
    settings: Settings,
) -> dict[str, Any]:
    if sum(len(t.rows) for t in tables) > settings.max_total_rows:
        raise IngestError(f"Too many rows; the limit is {settings.max_total_rows}.")
    others = await meta.count_active_datasets(pool, exclude_visitor_id=visitor_id)
    if others >= settings.max_active_datasets:
        raise CapacityError("at capacity")
    schema = meta.new_schema_name()
    contexts = [build_table_context(t) for t in tables]
    try:
        return await _create(pool, schema, visitor_id, dataset_name, tables, contexts, settings)
    except asyncpg.UniqueViolationError as exc:
        raise IngestError("Another upload is already in progress. Try again in a moment.") from exc


async def _create(
    pool: asyncpg.Pool,
    schema: str,
    visitor_id: str,
    dataset_name: str,
    tables: list[FinalTable],
    contexts: list[dict[str, Any]],
    settings: Settings,
) -> dict[str, Any]:
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        for table in tables:
            ddl_cols = ", ".join(f'"{n}" {PG_TYPES[t]}' for n, t in table.columns)
            await conn.execute(f'CREATE TABLE "{schema}"."{table.name}" ({ddl_cols})')
            await conn.copy_records_to_table(
                table.name,
                records=table.rows,
                columns=[n for n, _ in table.columns],
                schema_name=schema,
            )
        await conn.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO ayd_reader')
        await conn.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{schema}" TO ayd_reader')
        return await meta.insert_dataset(
            conn,
            visitor_id=visitor_id,
            schema_name=schema,
            name=dataset_name,
            tables=contexts,
            ttl_hours=settings.dataset_ttl_hours,
        )
