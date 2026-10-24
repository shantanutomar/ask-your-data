"""Parse uploaded files into raw tables (lists of python scalars)."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

import pandas as pd

from ingest.types import normalize_cell


class IngestError(ValueError):
    """A problem with the user's data that can be shown to them."""


class CapacityError(Exception):
    """The shared demo database has reached its dataset cap."""


@dataclass
class RawTable:
    name: str
    columns: list[str]
    rows: list[list[Any]]


def _stem(filename: str) -> str:
    stem = PurePath(filename or "data").stem
    return re.sub(r"\s+", "_", stem) or "data"


def _frame_to_raw(name: str, df: pd.DataFrame) -> RawTable:
    columns = [str(c) if not str(c).startswith("Unnamed:") else "" for c in df.columns]
    rows = [[normalize_cell(v) for v in row] for row in df.itertuples(index=False, name=None)]
    return RawTable(name=name, columns=columns, rows=rows)


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return content.decode(encoding)
        except UnicodeError:
            continue
    return content.decode("latin-1")


def parse_csv(filename: str, content: bytes, max_rows: int) -> list[RawTable]:
    text = _decode(content)
    if not text.strip():
        raise IngestError("The file is empty.")
    try:
        sep = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        sep = ","
    try:
        df = pd.read_csv(
            io.StringIO(text),
            sep=sep,
            dtype=str,
            keep_default_na=False,
            nrows=max_rows + 1,
            skipinitialspace=True,
        )
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise IngestError(f"Could not read the CSV: {exc}") from exc
    return [_frame_to_raw(_stem(filename), df)]


def _records_to_raw(name: str, records: list[Any]) -> RawTable:
    if not records:
        raise IngestError(f"'{name}' has no rows.")
    if not all(isinstance(r, dict) for r in records):
        raise IngestError("JSON must be an array of objects (records).")
    columns: list[str] = []
    for rec in records:
        for key in rec:
            if key not in columns:
                columns.append(key)
    rows = [[normalize_cell(rec.get(c)) for c in columns] for rec in records]
    return RawTable(name=name, columns=columns, rows=rows)


def parse_json(filename: str, content: bytes) -> list[RawTable]:
    try:
        data = json.loads(_decode(content))
    except json.JSONDecodeError as exc:
        raise IngestError(f"Invalid JSON: {exc.msg} (line {exc.lineno}).") from exc
    stem = _stem(filename)
    if isinstance(data, list):
        return [_records_to_raw(stem, data)]
    if isinstance(data, dict):
        if data and all(isinstance(v, list) for v in data.values()):
            return [_records_to_raw(str(k), v) for k, v in data.items()]
        return [_records_to_raw(stem, [data])]
    raise IngestError("JSON must be an array of objects or an object of arrays.")


def parse_xlsx(filename: str, content: bytes, max_rows: int) -> list[RawTable]:
    try:
        sheets = pd.read_excel(
            io.BytesIO(content), sheet_name=None, dtype=object, nrows=max_rows + 1
        )
    except Exception as exc:  # openpyxl raises a zoo of exception types
        raise IngestError(f"Could not read the Excel file: {type(exc).__name__}.") from exc
    tables = [_frame_to_raw(str(name), df) for name, df in sheets.items() if not df.empty]
    if not tables:
        raise IngestError("The workbook has no data.")
    return tables


def parse_file(filename: str, content: bytes, max_rows: int) -> list[RawTable]:
    ext = PurePath(filename or "").suffix.lower()
    if ext in (".csv", ".tsv", ".txt"):
        return parse_csv(filename, content, max_rows)
    if ext == ".json":
        return parse_json(filename, content)
    if ext in (".xlsx", ".xlsm"):
        return parse_xlsx(filename, content, max_rows)
    raise IngestError("Unsupported file type. Upload a .csv, .json or .xlsx file.")
