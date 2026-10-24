"""The chat pipeline as an async generator of SSE event dicts.

gate -> persist -> (title) -> condense -> cache -> text-to-SQL -> validate+execute (retry)
     -> analysis stream  ||  chart spec -> finalize (persist, cache, gate) -> done
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import anyio
import asyncpg
from redis.asyncio import Redis

from config import Settings
from db import meta
from gate import Gate
from llm import LLMError, LLMProtocol
from pipeline import cache
from pipeline.analysis import ResultForAnalysis, stream_analysis
from pipeline.chart_spec import ChartTable, generate_chart_spec
from pipeline.condense import condense_question
from pipeline.models import PipelineError, QueryItem, SqlPlan
from pipeline.text_to_sql import generate_plan
from pipeline.title import generate_title
from sql.executor import QueryError, QueryResult, execute_query
from sql.schema_context import build_schema_context

logger = logging.getLogger("pipeline")

_USER_KEY_SENTINEL = "byok"


@dataclass
class ChatDeps:
    pool: asyncpg.Pool
    redis: Redis
    settings: Settings
    gate: Gate
    llm: LLMProtocol


@dataclass
class ChatRequest:
    visitor_id: str
    has_user_key: bool
    question: str
    conversation_id: str | None
    dataset: dict[str, Any]


@dataclass
class _Accumulator:
    tokens: list[str] = field(default_factory=list)
    sql: dict[str, Any] | None = None
    tables: list[dict[str, Any]] = field(default_factory=list)
    chart: dict[str, Any] | None = None
    status: str = "failed"
    error: str | None = None

    @property
    def content(self) -> str:
        return "".join(self.tokens) or (self.error or "")


def _status(step: str) -> dict[str, Any]:
    return {"type": "status", "step": step}


def _error(code: str, message: str) -> dict[str, Any]:
    return {"type": "error", "code": code, "message": message}


async def _run_plan(
    deps: ChatDeps, dataset: dict[str, Any], plan: SqlPlan
) -> list[tuple[QueryItem, QueryResult]]:
    if not plan.queries:
        raise QueryError("The plan contained no queries.")
    allowed = {t["name"] for t in dataset["tables"]}
    results = []
    for item in plan.queries:
        result = await execute_query(
            deps.pool,
            schema_name=dataset["schema_name"],
            sql=item.sql,
            allowed_tables=allowed,
            max_rows=deps.settings.max_result_rows,
            timeout_ms=deps.settings.sql_statement_timeout_ms,
        )
        results.append((item, result))
    return results


async def _finalize(deps: ChatDeps, conversation_id: str, message_id: str, acc: _Accumulator):
    # Shielded so a client disconnect (task cancellation) still persists partial output.
    with anyio.CancelScope(shield=True):
        try:
            await meta.finalize_message(
                deps.pool,
                message_id,
                content=acc.content,
                sql=acc.sql,
                tables=acc.tables or None,
                chart=acc.chart,
                status=acc.status,
            )
            await meta.touch_conversation(deps.pool, conversation_id)
        except Exception:
            logger.exception("failed to finalize message")


async def run_chat(deps: ChatDeps, req: ChatRequest) -> AsyncIterator[dict[str, Any]]:
    settings, dataset = deps.settings, req.dataset
    user_key = _USER_KEY_SENTINEL if req.has_user_key else None

    gate_status = await deps.gate.check(req.visitor_id, user_key)
    if gate_status.mode == "blocked":
        yield _error(
            "blocked",
            "You've used your free tries. Enter your own OpenAI API key to continue.",
        )
        return

    # --- persist rows before streaming
    is_new = True
    conversation_id = None
    if req.conversation_id:
        conv = await meta.get_conversation(deps.pool, req.conversation_id, dataset["id"])
        if conv is not None:
            conversation_id, is_new = conv["id"], conv["title"] is None
    if conversation_id is None:
        conversation_id = await meta.create_conversation(deps.pool, dataset["id"])
    history = await meta.recent_history(deps.pool, conversation_id)
    await meta.insert_message(deps.pool, conversation_id, "user", req.question, "completed")
    message_id = await meta.insert_message(deps.pool, conversation_id, "assistant", "", "streaming")
    yield {"type": "init", "conversation_id": conversation_id, "message_id": message_id}

    acc = _Accumulator()
    finalized = False
    title_task: asyncio.Task[str] | None = None
    chart_task: asyncio.Task | None = None
    try:
        if is_new:
            title_task = asyncio.create_task(
                generate_title(deps.llm, settings.model_fast, req.question)
            )

        question = await condense_question(deps.llm, settings.model_fast, req.question, history)
        key = cache.cache_key(settings.gate_namespace, dataset["id"], dataset["version"], question)
        cached = await cache.get_plan(deps.redis, key)
        plan: SqlPlan | None = None
        cache_hit = False
        if cached is not None:
            try:
                plan, cache_hit = SqlPlan.model_validate(cached), True
            except ValueError:
                plan = None

        yield _status("reading_schema")
        schema_context = build_schema_context(dataset["tables"])

        # --- text-to-SQL + execute with retry loop
        previous: SqlPlan | None = None
        last_error: str | None = None
        results: list[tuple[QueryItem, QueryResult]] = []
        attempts = 0
        while True:
            if plan is None:
                yield _status("writing_sql")
                plan = await generate_plan(
                    deps.llm, settings.model_sql, schema_context, question, previous, last_error
                )
            if plan.clarification_question:
                break
            yield _status("running_query")
            try:
                results = await _run_plan(deps, dataset, plan)
                break
            except QueryError as exc:
                logger.info("query failed (attempt %d): %s", attempts, exc)
                if attempts >= settings.max_sql_retries:
                    raise PipelineError(
                        "bad_sql",
                        "I couldn't build a working query for that. Try rephrasing the question.",
                    ) from exc
                attempts += 1
                previous, last_error, plan, cache_hit = plan, str(exc), None, False

        if title_task is not None:
            title = await title_task
            await meta.set_conversation_title(deps.pool, conversation_id, title)
            yield {"type": "title", "title": title}
            title_task = None

        if plan.clarification_question:
            acc.tokens.append(plan.clarification_question)
            yield {"type": "analysis_token", "token": plan.clarification_question}
        else:
            acc.sql = {
                "queries": [q.model_dump() for q in plan.queries],
                "cache_hit": cache_hit,
                "answer_format": plan.answer_format,
            }
            yield {"type": "sql", **acc.sql}

            chart_tables: list[ChartTable] = []
            for i, (item, res) in enumerate(results, start=1):
                table = {
                    "type": "table",
                    "table_id": f"t{i}",
                    "title": item.title,
                    "columns": res.columns,
                    "rows": res.rows,
                    "truncated": res.truncated,
                }
                if plan.answer_format != "text":
                    acc.tables.append({k: v for k, v in table.items() if k != "type"})
                    yield table
                chart_tables.append(ChartTable(f"t{i}", item.title, res.columns, res.rows))

            wants_chart = plan.answer_format in ("chart", "mixed") and any(
                t.rows for t in chart_tables
            )
            if wants_chart:
                chart_task = asyncio.create_task(
                    generate_chart_spec(deps.llm, settings.model_fast, question, chart_tables)
                )

            yield _status("analysing")
            analysis_input = [
                ResultForAnalysis(item.title, res.columns, res.rows, res.truncated)
                for item, res in results
            ]
            async for token in stream_analysis(
                deps.llm, settings.model_sql, question, analysis_input
            ):
                acc.tokens.append(token)
                yield {"type": "analysis_token", "token": token}

            if chart_task is not None:
                spec = await chart_task
                chart_task = None
                if spec is not None:
                    acc.chart = spec.model_dump()
                    yield {"type": "chart", "spec": acc.chart}

            if not cache_hit:
                await cache.put_plan(
                    deps.redis,
                    key,
                    {
                        "queries": [q.model_dump() for q in plan.queries],
                        "clarification_question": None,
                        "answer_format": plan.answer_format,
                    },
                )

        acc.status = "completed"
        await _finalize(deps, conversation_id, message_id, acc)
        finalized = True

        remaining = gate_status.remaining
        mode = gate_status.mode
        if gate_status.mode == "free":
            try:
                remaining = await deps.gate.consume(req.visitor_id)
                mode = "free" if remaining > 0 else "blocked"
            except Exception:
                logger.exception("gate.consume failed")
        yield {"type": "done", "gate": {"mode": mode, "remaining": remaining}}

    except (asyncio.CancelledError, GeneratorExit):
        acc.status = "cancelled"
        raise
    except PipelineError as exc:
        acc.error = exc.message
        yield _error(exc.code, exc.message)
    except LLMError as exc:
        acc.error = exc.message
        yield _error(exc.code, exc.message)
    except Exception:
        logger.exception("chat pipeline failed")
        acc.error = "Something went wrong while answering. Please try again."
        yield _error("internal", acc.error)
    finally:
        for task in (title_task, chart_task):
            if task is not None and not task.done():
                task.cancel()
        if not finalized:
            await _finalize(deps, conversation_id, message_id, acc)
