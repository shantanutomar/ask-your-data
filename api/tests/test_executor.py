import pytest

from sql.executor import QueryError, execute_query

TABLES = {"customers", "products", "orders", "order_items"}


async def run(pool, ds, sql, max_rows=500, timeout_ms=5000):
    return await execute_query(
        pool,
        schema_name=ds["schema_name"],
        sql=sql,
        allowed_tables=TABLES,
        max_rows=max_rows,
        timeout_ms=timeout_ms,
    )


async def test_runs_aggregate_query(pool, sample_dataset):
    res = await run(
        pool,
        sample_dataset,
        'SELECT status, count(*) AS n FROM "orders" GROUP BY 1 ORDER BY 2 DESC',
    )
    assert res.columns == ["status", "n"]
    assert sum(r[1] for r in res.rows) == 1500
    assert not res.truncated


async def test_truncation_flag(pool, sample_dataset):
    res = await run(pool, sample_dataset, "SELECT * FROM orders", max_rows=10)
    assert len(res.rows) == 10 and res.truncated


async def test_empty_result_keeps_columns(pool, sample_dataset):
    res = await run(pool, sample_dataset, "SELECT id, status FROM orders WHERE id < 0")
    assert res.columns == ["id", "status"] and res.rows == []


async def test_json_safe_values(pool, sample_dataset):
    res = await run(pool, sample_dataset, "SELECT order_date, total_amount FROM orders LIMIT 1")
    assert isinstance(res.rows[0][0], str)
    assert isinstance(res.rows[0][1], (int, float))


async def test_statement_timeout(pool, sample_dataset):
    with pytest.raises(QueryError, match="too long"):
        await run(
            pool,
            sample_dataset,
            "SELECT count(*) FROM generate_series(1, 100000000) a",
            timeout_ms=100,
        )


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE orders",
        "SELECT * FROM pg_catalog.pg_class",
        "SELECT * FROM app.datasets",
        "SELECT pg_sleep(1)",
        "SELECT 1; DELETE FROM orders",
    ],
)
async def test_blocked_queries_raise_query_error(pool, sample_dataset, sql):
    with pytest.raises(QueryError):
        await run(pool, sample_dataset, sql)


async def test_db_error_is_a_clean_message(pool, sample_dataset):
    with pytest.raises(QueryError) as exc:
        await run(pool, sample_dataset, "SELECT nonexistent_col FROM orders")
    assert "nonexistent_col" in str(exc.value)
    assert "Traceback" not in str(exc.value)


async def test_reader_role_cannot_write_or_see_app_schema(pool, sample_dataset):
    """Defence in depth: even bypassing the validator the role itself is locked down."""
    schema = sample_dataset["schema_name"]
    async with pool.acquire() as conn:
        for stmt in (
            f'DELETE FROM "{schema}"."orders"',
            f'DROP TABLE "{schema}"."orders"',
            "SELECT * FROM app.datasets",
        ):
            with pytest.raises(Exception):  # noqa: B017
                async with conn.transaction():
                    await conn.execute("SET LOCAL ROLE ayd_reader")
                    await conn.execute(stmt)


async def test_reader_cannot_read_another_dataset(pool, sample_dataset):
    import uuid

    from db import meta

    other = f"other-{uuid.uuid4().hex}"
    from config import get_settings
    from ingest.commit import apply_edits, create_dataset
    from ingest.drafts import build_draft
    from ingest.parsers import RawTable

    s = get_settings()
    draft = build_draft(
        [RawTable("t", ["a"], [["1"]])], visitor_id=other, dataset_name="o", settings=s
    )
    ds2 = await create_dataset(
        pool, visitor_id=other, dataset_name="o", tables=apply_edits(draft, None, s), settings=s
    )
    try:
        with pytest.raises(QueryError):
            await execute_query(
                pool,
                schema_name=sample_dataset["schema_name"],
                sql=f'SELECT * FROM "{ds2["schema_name"]}".t',
                allowed_tables={"t"},
                max_rows=10,
                timeout_ms=1000,
            )
    finally:
        await meta.delete_dataset(pool, other)
