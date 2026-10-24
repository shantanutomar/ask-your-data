"""Free-taste gate: N free AI actions per visitor, then bring your own key.

Standalone and provider-agnostic: depends only on an async Redis client. Copy this folder into
another project unchanged; `test_gate.py` is the portable spec.

    status = await gate.check(visitor_id, user_key)   # BEFORE any LLM call
    if status.mode == "blocked": ...                  # ask for a key
    ... run the AI action ...
    if status.mode == "free": await gate.consume(visitor_id)   # ONLY after it succeeded
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from redis.asyncio import Redis

Mode = Literal["byok", "free", "blocked"]


@dataclass(frozen=True)
class GateStatus:
    mode: Mode
    remaining: int | None  # None for byok (unlimited)


class Gate:
    def __init__(
        self, redis: Redis, *, free_actions: int = 3, namespace: str = "app", ttl_days: int = 7
    ) -> None:
        self._redis = redis
        self._free = free_actions
        self._namespace = namespace
        self._ttl_seconds = ttl_days * 86400

    def _key(self, visitor_id: str) -> str:
        return f"{self._namespace}:gate:{visitor_id}"

    async def _used(self, visitor_id: str) -> int:
        value = await self._redis.get(self._key(visitor_id))
        return int(value) if value else 0

    async def check(self, visitor_id: str, user_key: str | None = None) -> GateStatus:
        if user_key:
            return GateStatus("byok", None)
        remaining = max(self._free - await self._used(visitor_id), 0)
        return GateStatus("free" if remaining > 0 else "blocked", remaining)

    async def consume(self, visitor_id: str) -> int:
        """Record one successful free action; returns the remaining free actions."""
        key = self._key(visitor_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, self._ttl_seconds, nx=True)
            used, _ = await pipe.execute()
        return max(self._free - int(used), 0)
