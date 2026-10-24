from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

AnswerFormat = Literal["text", "table", "chart", "mixed"]


class PipelineError(Exception):
    """An expected failure that is shown to the user as an SSE `error` event."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class QueryItem(BaseModel):
    title: str
    sql: str


class SqlPlan(BaseModel):
    queries: list[QueryItem]
    clarification_question: str | None
    answer_format: AnswerFormat


class ChartSpec(BaseModel):
    type: Literal["bar", "line", "area", "pie", "scatter"]
    title: str
    table_id: str
    x: str
    y: list[str]
    series: str | None
    x_label: str | None
    y_label: str | None
