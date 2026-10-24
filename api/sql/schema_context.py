"""Build the schema description handed to the text-to-SQL prompt."""

from __future__ import annotations

import json
from typing import Any


def _literal(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def build_schema_context(tables: list[dict[str, Any]]) -> str:
    """Tables, columns+types, value hints for low-cardinality text columns, and sample rows."""
    parts: list[str] = []
    for table in tables:
        lines = [f'TABLE "{table["name"]}" ({table["row_count"]} rows)']
        for col in table["columns"]:
            line = f'  "{col["name"]}" {col["type"]}'
            if col.get("distinct"):
                line += "  -- exact values: " + ", ".join(_literal(v) for v in col["distinct"])
            elif "min" in col and col["min"] is not None:
                line += f"  -- range: {col['min']} to {col['max']}"
            lines.append(line)
        samples = table.get("samples") or []
        if samples:
            lines.append("  sample rows:")
            lines.extend("    " + json.dumps(s, default=str, ensure_ascii=False) for s in samples)
        parts.append("\n".join(lines))
    return "\n\n".join(parts)
