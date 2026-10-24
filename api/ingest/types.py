"""Column type inference and value coercion for ingested data."""

from __future__ import annotations

import datetime as dt
import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

ColumnType = Literal["text", "integer", "numeric", "boolean", "date", "timestamp"]
COLUMN_TYPES: tuple[str, ...] = ("text", "integer", "numeric", "boolean", "date", "timestamp")

PG_TYPES: dict[str, str] = {
    "text": "text",
    "integer": "bigint",
    "numeric": "numeric",
    "boolean": "boolean",
    "date": "date",
    "timestamp": "timestamp",
}

NULL_STRINGS = frozenset({"", "null", "nan", "n/a"})
_TRUE = frozenset({"true", "yes", "t", "y", "1"})
_FALSE = frozenset({"false", "no", "f", "n", "0"})

_INT_RE = re.compile(r"^[+-]?(0|[1-9]\d*)$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:?\d{2})?$")
_MAX_INT_DIGITS = 18


def normalize_cell(value: Any) -> Any:
    """Make a parsed cell a plain python scalar; blanks/NaN become None."""
    if value is None:
        return None
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, str):
        value = value.strip()
        return None if value.lower() in NULL_STRINGS else value
    if isinstance(value, dt.datetime) and value != value:  # NaT
        return None
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, default=str)
    return value


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer" if len(str(abs(value))) <= _MAX_INT_DIGITS else "text"
    if isinstance(value, float):
        return "integer" if value.is_integer() and abs(value) < 1e15 else "numeric"
    if isinstance(value, dt.datetime):
        return "date" if value.time() == dt.time(0) and value.tzinfo is None else "timestamp"
    if isinstance(value, dt.date):
        return "date"
    s = str(value).strip()
    low = s.lower()
    if low in ("true", "false", "yes", "no"):
        return "boolean"
    if _INT_RE.match(s):
        return "integer" if len(s.lstrip("+-")) <= _MAX_INT_DIGITS else "text"
    if _FLOAT_RE.match(s) and not re.match(r"^[+-]?0\d", s):
        return "numeric"
    if _DATE_RE.match(s):
        try:
            dt.date.fromisoformat(s)
        except ValueError:
            return "text"
        return "date"
    if _TS_RE.match(s):
        try:
            dt.datetime.fromisoformat(s)
        except ValueError:
            return "text"
        return "timestamp"
    return "text"


def infer_type(values: list[Any]) -> ColumnType:
    kinds: set[str] = set()
    for v in values:
        if v is None:
            continue
        kinds.add(_kind(v))
        if "text" in kinds:
            return "text"
    if not kinds:
        return "text"
    if len(kinds) == 1:
        return kinds.pop()  # type: ignore[return-value]
    if kinds <= {"integer", "numeric"}:
        return "numeric"
    if kinds <= {"date", "timestamp"}:
        return "timestamp"
    return "text"


def canonical(value: Any, col_type: str) -> Any:
    """JSON-safe representation stored in the Redis draft."""
    if value is None:
        return None
    if col_type == "integer":
        return int(Decimal(str(value))) if not isinstance(value, bool) else int(value)
    if col_type == "numeric":
        return str(value)
    if col_type == "boolean":
        return coerce(value, "boolean")
    if col_type in ("date", "timestamp"):
        v = coerce(value, col_type)
        return v.isoformat()
    return value if isinstance(value, str) else _to_text(value)


def _to_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return str(value)


class CoerceError(ValueError):
    pass


def coerce(value: Any, col_type: str) -> Any:
    """Convert a canonical/raw value into the python type asyncpg expects for `col_type`."""
    if value is None:
        return None
    try:
        if col_type == "text":
            return _to_text(value)
        if col_type == "integer":
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            d = Decimal(str(value).strip())
            if d != d.to_integral_value():
                raise CoerceError("not an integer")
            result = int(d)
            if abs(result) >= 2**63:
                raise CoerceError("integer out of range")
            return result
        if col_type == "numeric":
            if isinstance(value, bool):
                raise CoerceError("not a number")
            d = Decimal(str(value).strip())
            if not d.is_finite():
                raise CoerceError("not a finite number")
            return d
        if col_type == "boolean":
            if isinstance(value, bool):
                return value
            s = str(value).strip().lower()
            if s in _TRUE:
                return True
            if s in _FALSE:
                return False
            raise CoerceError("not a boolean")
        if col_type == "date":
            if isinstance(value, dt.datetime):
                return value.date()
            if isinstance(value, dt.date):
                return value
            s = str(value).strip()
            return dt.date.fromisoformat(s[:10]) if _DATE_RE.match(s[:10]) else _fail("date")
        if col_type == "timestamp":
            if isinstance(value, dt.datetime):
                parsed = value
            elif isinstance(value, dt.date):
                parsed = dt.datetime.combine(value, dt.time())
            else:
                s = str(value).strip()
                if _DATE_RE.match(s):
                    parsed = dt.datetime.combine(dt.date.fromisoformat(s), dt.time())
                else:
                    parsed = dt.datetime.fromisoformat(s)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(dt.UTC).replace(tzinfo=None)
            return parsed
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise CoerceError(str(exc) or f"not a valid {col_type}") from exc
    raise CoerceError(f"unknown column type {col_type}")


def _fail(kind: str) -> Any:
    raise CoerceError(f"not a valid {kind}")


def sanitize_identifier(raw: Any, taken: set[str], fallback: str = "col") -> str:
    """snake_case `[a-z_][a-z0-9_]*`, de-duplicated against `taken` (which is updated)."""
    text = unicodedata.normalize("NFKD", str(raw)).encode("ascii", "ignore").decode()
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    text = re.sub(r"[^a-z0-9_]+", "_", text.lower())
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = fallback
    if text[0].isdigit():
        text = f"c_{text}"
    text = text[:50]
    candidate, i = text, 2
    while candidate in taken:
        candidate = f"{text}_{i}"
        i += 1
    taken.add(candidate)
    return candidate
