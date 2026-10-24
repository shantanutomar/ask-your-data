from __future__ import annotations

from datetime import date

from llm import LLMProtocol
from pipeline.models import SqlPlan

SYSTEM = """You are a careful PostgreSQL data analyst. Turn the user's question into SQL over the \
tables described below.

Rules:
- Write read-only SQL: a single SELECT (CTEs allowed) per query. No semicolon-separated statements.
- Use plain table names with no schema prefix, and always double-quote table and column names.
- Use only the tables and columns listed. Never invent columns or tables.
- Text matching: when a column lists its exact values, use them exactly as written. For other text \
columns use ILIKE '%term%' instead of =.
- Today's date is {today}. Resolve relative dates ("last month", "this year") against it.
- Aggregate in SQL. Do not return thousands of raw rows when a summary answers the question. Add \
ORDER BY, and a sensible LIMIT for rankings (for example top 10).
- When grouping by month/week/day, cast: DATE_TRUNC('month', "col")::date.
- Round computed decimals to 2 places; cast to numeric before dividing integers.
- Return 1 to 3 queries, each with a short human-readable title.
- If the question is ambiguous or cannot be answered from these tables, set clarification_question \
to one short question for the user and return no queries.
- answer_format: "text" for a single fact or number, "table" for a list of rows, "chart" for a \
trend, comparison or distribution best seen visually, "mixed" for a written answer plus a table \
and/or chart."""


def build_user_prompt(
    schema_context: str,
    question: str,
    previous: SqlPlan | None = None,
    error: str | None = None,
) -> str:
    prompt = f"Tables:\n{schema_context}\n\nQuestion: {question}"
    if previous is not None and error:
        attempts = "\n".join(f"-- {q.title}\n{q.sql}" for q in previous.queries)
        prompt += (
            f"\n\nYour previous attempt failed.\nSQL:\n{attempts}\nError: {error}\n"
            "Fix the problem and return corrected queries."
        )
    return prompt


async def generate_plan(
    llm: LLMProtocol,
    model: str,
    schema_context: str,
    question: str,
    previous: SqlPlan | None = None,
    error: str | None = None,
) -> SqlPlan:
    return await llm.structured(
        step="text_to_sql",
        model=model,
        system=SYSTEM.format(today=date.today().isoformat()),
        user=build_user_prompt(schema_context, question, previous, error),
        schema=SqlPlan,
    )
