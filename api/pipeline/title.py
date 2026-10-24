from __future__ import annotations

from pydantic import BaseModel

from llm import LLMError, LLMProtocol

SYSTEM = (
    "Write a short title (max 6 words, no quotes, no trailing punctuation) for a data-analysis "
    "chat that starts with the user's question."
)


class _Title(BaseModel):
    title: str


def fallback_title(question: str) -> str:
    q = question.strip().replace("\n", " ")
    return q if len(q) <= 50 else q[:47].rstrip() + "..."


async def generate_title(llm: LLMProtocol, model: str, question: str) -> str:
    try:
        result = await llm.structured(
            step="title", model=model, system=SYSTEM, user=question, schema=_Title
        )
    except LLMError:
        return fallback_title(question)
    title = result.title.strip().strip("\"'")
    return title[:80] or fallback_title(question)
