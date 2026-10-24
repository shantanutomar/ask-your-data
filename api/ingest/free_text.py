"""Extract tables from pasted free text with an LLM (one gate action)."""

from __future__ import annotations

from pydantic import BaseModel

from ingest.parsers import IngestError, RawTable
from ingest.types import normalize_cell
from llm import LLMProtocol

SYSTEM = """Extract structured tables from the user's pasted text.
- Return one or more tables. Prefer a single table unless the text clearly contains separate entities.
- Each table: a short snake_case name, a list of column names, and rows as lists of strings \
(one string per column, null when a value is missing).
- Copy values exactly as they appear. Do not invent rows, correct values or add data that is not in the text.
- Keep numbers and dates as written (no currency symbols or thousands separators in numbers).
- If the text contains no tabular or list-like data, return no tables."""


class _ExtractedTable(BaseModel):
    name: str
    columns: list[str]
    rows: list[list[str | None]]


class _Extraction(BaseModel):
    tables: list[_ExtractedTable]


async def extract_tables(llm: LLMProtocol, model: str, text: str) -> list[RawTable]:
    result = await llm.structured(
        step="free_text_extract", model=model, system=SYSTEM, user=text, schema=_Extraction
    )
    tables = [
        RawTable(
            name=t.name,
            columns=t.columns,
            rows=[[normalize_cell(v) for v in row] for row in t.rows],
        )
        for t in result.tables
        if t.columns and t.rows
    ]
    if not tables:
        raise IngestError(
            "I couldn't find any tabular data in that text. Try pasting a list or a table."
        )
    return tables
