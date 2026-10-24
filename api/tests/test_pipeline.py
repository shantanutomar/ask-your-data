from __future__ import annotations

import asyncio

import pytest

from config import get_settings
from db import meta
from pipeline.models import ChartSpec, QueryItem, SqlPlan
from pipeline.orchestrator import ChatDeps, ChatRequest, run_chat


class StubLLM:
    """Scripted LLM: `plans` are returned in order by the text_to_sql step."""

    def __init__(self, plans, chart=None, tokens=("Hello ", "world.")):
        self.plans = list(plans)
        self.chart = chart
        self.tokens = tokens
        self.calls: list[str] = []

    async def structured(self, *, step, model, system, user, schema):
        self.calls.append(step)
        if step == "title":
            return schema(title="Orders by status")
        if step == "condense":
            return schema(question=user.rsplit("Latest message: ", 1)[1])
        if step == "text_to_sql":
            return self.plans.pop(0)
        if step == "chart_spec":
            return self.chart
        raise AssertionError(step)

    async def stream(self, *, step, model, system, user):
        self.calls.append(step)
        for t in self.tokens:
            await asyncio.sleep(0)
            yield t

    async def validate_key(self):
        return True

    async def aclose(self):
        pass


def plan(sql, fmt="mixed", clarification=None):
    queries = [] if clarification else [QueryItem(title="Orders by status", sql=sql)]
    return SqlPlan(queries=queries, clarification_question=clarification, answer_format=fmt)


GOOD_SQL = 'SELECT status, count(*) AS n FROM "orders" GROUP BY 1 ORDER BY 2 DESC'
CHART = ChartSpec(
    type="bar", title="Orders", table_id="t1", x="status", y=["n"], series=None,
    x_label=None, y_label=None,
)  # fmt: skip


def make_deps(pool, redis, gate, llm):
    return ChatDeps(pool=pool, redis=redis, settings=get_settings(), gate=gate, llm=llm)


def make_req(visitor_id, dataset, question="How many orders per status?", conv=None, key=False):
    return ChatRequest(
        visitor_id=visitor_id, has_user_key=key, question=question,
        conversation_id=conv, dataset=dataset,
    )  # fmt: skip


async def collect(gen):
    return [e async for e in gen]


async def test_happy_path_then_cache_hit(pool, redis, gate, sample_dataset, visitor_id):
    llm = StubLLM([plan(GOOD_SQL)], chart=CHART)
    deps = make_deps(pool, redis, gate, llm)
    events = await collect(run_chat(deps, make_req(visitor_id, sample_dataset)))
    types = [e["type"] for e in events]
    assert types[0] == "init"
    assert types.index("title") < types.index("sql") or "title" in types
    for needed in ("status", "sql", "table", "analysis_token", "chart", "done"):
        assert needed in types
    assert types[-1] == "done"
    steps = [e["step"] for e in events if e["type"] == "status"]
    assert steps == ["reading_schema", "writing_sql", "running_query", "analysing"]
    sql_event = next(e for e in events if e["type"] == "sql")
    assert sql_event["cache_hit"] is False
    table = next(e for e in events if e["type"] == "table")
    assert table["table_id"] == "t1" and table["columns"] == ["status", "n"]
    assert events[-1]["gate"] == {"mode": "free", "remaining": 2}

    conv_id = events[0]["conversation_id"]
    msgs = await meta.list_messages(pool, conv_id)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["status"] == "completed" and msgs[1]["content"] == "Hello world."
    assert msgs[1]["chart"]["type"] == "bar" and msgs[1]["tables"][0]["table_id"] == "t1"
    conv = await meta.get_conversation(pool, conv_id, sample_dataset["id"])
    assert conv["title"] == "Orders by status"

    # same question again, same conversation: condense runs, SQL comes from cache
    llm2 = StubLLM([], chart=CHART)
    events2 = await collect(
        run_chat(
            make_deps(pool, redis, gate, llm2), make_req(visitor_id, sample_dataset, conv=conv_id)
        )
    )
    assert "text_to_sql" not in llm2.calls
    assert next(e for e in events2 if e["type"] == "sql")["cache_hit"] is True
    assert not any(e["type"] == "title" for e in events2)  # existing conversation
    assert events2[-1]["gate"]["remaining"] == 1


async def test_text_format_emits_no_table_or_chart(pool, redis, gate, sample_dataset, visitor_id):
    llm = StubLLM([plan("SELECT count(*) AS n FROM orders", fmt="text")], chart=CHART)
    events = await collect(
        run_chat(make_deps(pool, redis, gate, llm), make_req(visitor_id, sample_dataset))
    )
    types = [e["type"] for e in events]
    assert "table" not in types and "chart" not in types and types[-1] == "done"


async def test_retry_on_bad_sql_then_success(pool, redis, gate, sample_dataset, visitor_id):
    llm = StubLLM([plan("SELECT nope FROM orders"), plan(GOOD_SQL)], chart=CHART)
    events = await collect(
        run_chat(make_deps(pool, redis, gate, llm), make_req(visitor_id, sample_dataset))
    )
    assert llm.calls.count("text_to_sql") == 2
    assert events[-1]["type"] == "done"
    assert next(e for e in events if e["type"] == "sql")["queries"][0]["sql"] == GOOD_SQL


async def test_gives_up_after_max_retries_and_does_not_charge(
    pool, redis, gate, sample_dataset, visitor_id
):
    bad = "SELECT nope FROM orders"
    llm = StubLLM([plan(bad), plan(bad), plan(bad)])
    events = await collect(
        run_chat(make_deps(pool, redis, gate, llm), make_req(visitor_id, sample_dataset))
    )
    assert events[-1]["type"] == "error" and events[-1]["code"] == "bad_sql"
    assert llm.calls.count("text_to_sql") == 3
    assert (await gate.check(visitor_id)).remaining == 3
    msgs = await meta.list_messages(pool, events[0]["conversation_id"])
    assert msgs[1]["status"] == "failed"


async def test_malicious_sql_never_executes(pool, redis, gate, sample_dataset, visitor_id):
    evil = "DROP TABLE orders"
    llm = StubLLM([plan(evil), plan(evil), plan(evil)])
    events = await collect(
        run_chat(make_deps(pool, redis, gate, llm), make_req(visitor_id, sample_dataset))
    )
    assert events[-1]["code"] == "bad_sql"
    n = await pool.fetchval(f'SELECT count(*) FROM "{sample_dataset["schema_name"]}".orders')
    assert n == 1500


async def test_clarification_is_streamed_and_no_sql_runs(
    pool, redis, gate, sample_dataset, visitor_id
):
    llm = StubLLM([plan("", clarification="Which year do you mean?")])
    events = await collect(
        run_chat(make_deps(pool, redis, gate, llm), make_req(visitor_id, sample_dataset))
    )
    types = [e["type"] for e in events]
    assert "sql" not in types and "table" not in types
    token = next(e for e in events if e["type"] == "analysis_token")
    assert token["token"] == "Which year do you mean?"
    assert types[-1] == "done"


async def test_blocked_when_free_actions_used(pool, redis, gate, sample_dataset, visitor_id):
    for _ in range(3):
        await gate.consume(visitor_id)
    llm = StubLLM([])
    events = await collect(
        run_chat(make_deps(pool, redis, gate, llm), make_req(visitor_id, sample_dataset))
    )
    assert events == [events[0]] and events[0]["code"] == "blocked"
    assert llm.calls == []


async def test_byok_bypasses_gate_and_is_not_counted(pool, redis, gate, sample_dataset, visitor_id):
    for _ in range(3):
        await gate.consume(visitor_id)
    llm = StubLLM([plan(GOOD_SQL, fmt="table")])
    events = await collect(
        run_chat(make_deps(pool, redis, gate, llm), make_req(visitor_id, sample_dataset, key=True))
    )
    assert events[-1]["type"] == "done" and events[-1]["gate"]["mode"] == "byok"
    assert await gate._used(visitor_id) == 3


async def test_cancel_marks_message_cancelled_and_keeps_partial_output(
    pool, redis, gate, sample_dataset, visitor_id
):
    llm = StubLLM([plan(GOOD_SQL, fmt="table")], tokens=("partial ", "more ", "text"))
    gen = run_chat(make_deps(pool, redis, gate, llm), make_req(visitor_id, sample_dataset))
    conv_id = None
    async for event in gen:
        if event["type"] == "init":
            conv_id = event["conversation_id"]
        if event["type"] == "analysis_token":
            break
    await gen.aclose()
    msgs = await meta.list_messages(pool, conv_id)
    assert msgs[1]["status"] == "cancelled"
    assert msgs[1]["content"].startswith("partial")
    assert (await gate.check(visitor_id)).remaining == 3


@pytest.mark.parametrize("question", ["a", "  spaced   out  "])
async def test_cache_key_normalisation(question):
    from pipeline.cache import cache_key, normalize_question

    assert normalize_question("  Hello   WORLD ") == "hello world"
    assert cache_key("ns", "d", 1, "A  b") == cache_key("ns", "d", 1, " a b ")
    assert cache_key("ns", "d", 1, question) != cache_key("ns", "d", 2, question)
