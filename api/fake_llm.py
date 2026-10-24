"""Offline stand-in for the LLM (FAKE_LLM=1): canned but schema-aware, for UI work and demos."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_TABLE_RE = re.compile(r'TABLE "([^"]+)"')
_TEXT_COL_RE = re.compile(r'^\s+"([^"]+)" text', re.MULTILINE)
_COLUMNS_RE = re.compile(r"columns: (\[.*?\])")
_LATEST_RE = re.compile(r"Latest message: (.*)$", re.DOTALL)


class FakeLLM:
    async def structured(
        self, *, step: str, model: str, system: str, user: str, schema: type[T]
    ) -> T:
        fields: dict[str, Any]
        if step == "title":
            fields = {"title": "Fake demo chat"}
        elif step == "condense":
            m = _LATEST_RE.search(user)
            fields = {"question": m.group(1).strip() if m else user}
        elif step == "text_to_sql":
            table = (_TABLE_RE.search(user) or [None, "data"])[1]
            text_col = _TEXT_COL_RE.search(user)
            if text_col:
                col = text_col.group(1)
                sql = (
                    f'SELECT "{col}", count(*) AS n FROM "{table}" '
                    f"GROUP BY 1 ORDER BY 2 DESC LIMIT 10"
                )
            else:
                sql = f'SELECT count(*) AS n FROM "{table}"'
            fields = {
                "queries": [{"title": f"Rows by {table}", "sql": sql}],
                "clarification_question": None,
                "answer_format": "mixed",
            }
        elif step == "chart_spec":
            m = _COLUMNS_RE.search(user)
            cols = json.loads(m.group(1)) if m else ["n"]
            fields = {
                "type": "bar",
                "title": "Fake chart",
                "table_id": "t1",
                "x": cols[0],
                "y": [cols[-1]],
                "series": None,
                "x_label": None,
                "y_label": None,
            }
        else:
            fields = {"tables": []}
        return schema.model_validate(fields)

    async def stream(self, *, step: str, model: str, system: str, user: str) -> AsyncIterator[str]:
        text = (
            "This is a **canned answer** from the offline fake model (`FAKE_LLM=1`). "
            "The SQL, table and chart above are real - they ran against your data.\n\n"
            "- Set `OPENAI_API_KEY` and unset `FAKE_LLM` for real answers."
        )
        for word in re.findall(r"\S+\s*", text):
            await asyncio.sleep(0.03)
            yield word

    async def validate_key(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None
