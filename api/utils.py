from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Any


def to_jsonable(value: Any) -> Any:
    """Convert a database value into something json.dumps can handle."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return None if value != value or value in (float("inf"), float("-inf")) else value
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dt.datetime):
        # date_trunc() on a date yields midnight UTC (timestamptz); show it as the plain date
        if (
            value.tzinfo is not None
            and value.utcoffset() == dt.timedelta(0)
            and value.time() == dt.time(0)
        ):
            return value.date().isoformat()
        return value.isoformat()
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    return str(value)


def sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"
