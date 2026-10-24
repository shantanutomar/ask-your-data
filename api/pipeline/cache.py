"""Exact-match SQL cache (stores the SQL plan, not results - queries re-run on live data)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from redis.asyncio import Redis

CACHE_TTL_SECONDS = 24 * 3600


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question.strip().lower())


def cache_key(namespace: str, dataset_id: str, version: int, question: str) -> str:
    digest = hashlib.sha256(normalize_question(question).encode()).hexdigest()
    return f"{namespace}:cache:{dataset_id}:{version}:{digest}"


async def get_plan(redis: Redis, key: str) -> dict[str, Any] | None:
    raw = await redis.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def put_plan(redis: Redis, key: str, plan: dict[str, Any]) -> None:
    await redis.set(key, json.dumps(plan), ex=CACHE_TTL_SECONDS)
