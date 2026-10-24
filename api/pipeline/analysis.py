from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from llm import LLMProtocol

MAX_ROWS_IN_PROMPT = 100

SYSTEM = """You are a data analyst explaining query results to a business user.
- Answer ONLY from the result tables provided. Never use outside knowledge and never invent numbers.
- Lead with the direct answer, then add the key supporting figures. Be concise.
- Use Markdown (short paragraphs or bullets, **bold** for key figures). Do not repeat whole tables; \
the user already sees them.
- If a result is empty, say no matching data was found.
- If a result is marked truncated, say only the first rows are shown and totals may be larger.
- Do not mention SQL unless asked."""


@dataclass
class ResultForAnalysis:
    title: str
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool


def build_user_prompt(question: str, results: list[ResultForAnalysis]) -> str:
    blocks = [f"Question: {question}"]
    for r in results:
        shown = r.rows[:MAX_ROWS_IN_PROMPT]
        note = f"{len(r.rows)} rows"
        if r.truncated:
            note += " (TRUNCATED: more rows exist than were returned)"
        if len(shown) < len(r.rows):
            note += f"; first {len(shown)} shown here"
        blocks.append(
            f"Result: {r.title} - {note}\ncolumns: {json.dumps(r.columns)}\n"
            f"rows: {json.dumps(shown, default=str)}"
        )
    return "\n\n".join(blocks)


def stream_analysis(
    llm: LLMProtocol, model: str, question: str, results: list[ResultForAnalysis]
) -> AsyncIterator[str]:
    return llm.stream(
        step="analysis",
        model=model,
        system=SYSTEM,
        user=build_user_prompt(question, results),
    )
