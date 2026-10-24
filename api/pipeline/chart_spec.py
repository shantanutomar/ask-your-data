from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from llm import LLMError, LLMProtocol
from pipeline.models import ChartSpec

logger = logging.getLogger("pipeline.chart")

SYSTEM = """You design a chart for query results. Return a declarative chart spec, never code.
- table_id: one of the provided result ids. x and every y must be exact column names of that table.
- y lists one or more numeric columns. series is an optional column that splits the data into \
colored groups (only when y has a single column), otherwise null.
- bar: category comparison. line/area: change over time (x is a date/time or ordered value). \
pie: share of a whole with a single y and at most 8 categories. scatter: two numeric columns.
- title is short; x_label and y_label are short human labels (or null)."""


@dataclass
class ChartTable:
    table_id: str
    title: str
    columns: list[str]
    rows: list[list[Any]]


def validate_spec(spec: ChartSpec, tables: list[ChartTable]) -> str | None:
    """Return a problem description, or None if the spec matches the real result columns."""
    table = next((t for t in tables if t.table_id == spec.table_id), None)
    if table is None:
        return f"table_id '{spec.table_id}' does not exist"
    cols = set(table.columns)
    if spec.x not in cols:
        return f"x column '{spec.x}' is not in {sorted(cols)}"
    if not spec.y:
        return "y must contain at least one column"
    for y in spec.y:
        if y not in cols:
            return f"y column '{y}' is not in {sorted(cols)}"
    if spec.series is not None and spec.series not in cols:
        return f"series column '{spec.series}' is not in {sorted(cols)}"
    if spec.type == "pie" and len(spec.y) != 1:
        return "a pie chart needs exactly one y column"
    return None


def _prompt(question: str, tables: list[ChartTable]) -> str:
    blocks = [f"Question: {question}"]
    for t in tables:
        blocks.append(
            f"Result id={t.table_id} title={t.title!r}\ncolumns: {json.dumps(t.columns)}\n"
            f"first rows: {json.dumps(t.rows[:5], default=str)} (total {len(t.rows)} rows)"
        )
    return "\n\n".join(blocks)


async def generate_chart_spec(
    llm: LLMProtocol, model: str, question: str, tables: list[ChartTable]
) -> ChartSpec | None:
    """Best effort: returns None (and the answer still streams) if no valid spec is produced."""
    user = _prompt(question, tables)
    for _ in range(2):
        try:
            spec = await llm.structured(
                step="chart_spec", model=model, system=SYSTEM, user=user, schema=ChartSpec
            )
        except LLMError as exc:
            logger.warning("chart spec failed: %s", exc.message)
            return None
        problem = validate_spec(spec, tables)
        if problem is None:
            return spec
        user = f"{_prompt(question, tables)}\n\nYour previous spec was invalid: {problem}. Fix it."
    return None
