from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel

from llm import LLMProtocol

SYSTEM = """Rewrite the user's latest message into a single standalone question about the data, \
using the conversation history only to resolve references such as "that", "those", "the same \
period" or "and for Germany?".
- If the message is already standalone, or unrelated to the history, return it unchanged.
- Keep the user's wording and intent. Do not answer the question. Do not add new filters.
- Today's date is {today}; keep relative dates ("last month") as the user wrote them.
Return only the rewritten question."""


class _Condensed(BaseModel):
    question: str


def _format_history(history: list[dict[str, Any]]) -> str:
    lines = []
    for msg in history:
        who = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{who}: {msg['content'][:400]}")
    return "\n".join(lines)


async def condense_question(
    llm: LLMProtocol, model: str, question: str, history: list[dict[str, Any]]
) -> str:
    if not history:
        return question
    result = await llm.structured(
        step="condense",
        model=model,
        system=SYSTEM.format(today=date.today().isoformat()),
        user=f"Conversation history:\n{_format_history(history)}\n\nLatest message: {question}",
        schema=_Condensed,
    )
    return result.question.strip() or question
