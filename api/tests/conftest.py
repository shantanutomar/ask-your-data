from __future__ import annotations

import os
import uuid

import asyncpg
import fakeredis
import pytest

from config import get_settings
from db.pool import create_pool, run_migrations
from gate import Gate

os.environ.setdefault("DATABASE_URL", "postgresql://localhost:5432/ask_your_data")


@pytest.fixture
async def pool():
    settings = get_settings()
    try:
        p = await create_pool(settings.database_url)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres not available: {exc}")
    await run_migrations(p)
    yield p
    await p.close()


@pytest.fixture
def redis():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def gate(redis):
    return Gate(redis, free_actions=3, namespace="test")


@pytest.fixture
def visitor_id():
    return f"test-{uuid.uuid4().hex}"


@pytest.fixture
async def sample_dataset(pool, visitor_id):
    """Load the bundled sample dataset for a throwaway visitor; clean up afterwards."""
    from db import meta
    from ingest.commit import apply_edits, create_dataset
    from ingest.drafts import build_draft
    from ingest.samples import load_sample_tables

    settings = get_settings()
    raw = load_sample_tables(settings.max_total_rows)
    draft = build_draft(raw, visitor_id=visitor_id, dataset_name="Sample", settings=settings)
    tables = apply_edits(draft, None, settings)
    dataset = await create_dataset(
        pool, visitor_id=visitor_id, dataset_name="Sample", tables=tables, settings=settings
    )
    yield dataset
    await meta.delete_dataset(pool, visitor_id)
