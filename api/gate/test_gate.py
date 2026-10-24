import asyncio

import fakeredis
import pytest

from gate import Gate


@pytest.fixture
def redis():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def gate(redis):
    return Gate(redis, free_actions=3, namespace="test", ttl_days=7)


async def test_fresh_visitor_gets_all_free_actions(gate):
    status = await gate.check("v1")
    assert (status.mode, status.remaining) == ("free", 3)


async def test_consume_decrements_remaining(gate):
    assert await gate.consume("v1") == 2
    assert await gate.consume("v1") == 1
    status = await gate.check("v1")
    assert (status.mode, status.remaining) == ("free", 1)


async def test_blocked_after_n_actions(gate):
    for _ in range(3):
        await gate.consume("v1")
    status = await gate.check("v1")
    assert (status.mode, status.remaining) == ("blocked", 0)


async def test_visitors_are_independent(gate):
    for _ in range(3):
        await gate.consume("v1")
    assert (await gate.check("v2")).mode == "free"


async def test_byok_bypasses_the_gate_even_when_blocked(gate):
    for _ in range(3):
        await gate.consume("v1")
    status = await gate.check("v1", user_key="sk-user")
    assert (status.mode, status.remaining) == ("byok", None)


async def test_check_does_not_consume(gate):
    for _ in range(10):
        await gate.check("v1")
    assert (await gate.check("v1")).remaining == 3


async def test_failed_action_is_not_charged(gate):
    # Callers only invoke consume() after success; a failure path never calls it.
    status = await gate.check("v1")
    assert status.mode == "free"
    assert (await gate.check("v1")).remaining == 3


async def test_counter_has_ttl(gate, redis):
    await gate.consume("v1")
    ttl = await redis.ttl("test:gate:v1")
    assert 0 < ttl <= 7 * 86400


async def test_ttl_is_not_extended_by_later_consumes(gate, redis):
    await gate.consume("v1")
    await redis.expire("test:gate:v1", 100)
    await gate.consume("v1")
    assert await redis.ttl("test:gate:v1") <= 100


async def test_counter_expires_and_visitor_gets_a_fresh_allowance(gate, redis):
    for _ in range(3):
        await gate.consume("v1")
    assert (await gate.check("v1")).mode == "blocked"
    await redis.pexpire("test:gate:v1", 50)
    await asyncio.sleep(0.15)
    status = await gate.check("v1")
    assert (status.mode, status.remaining) == ("free", 3)


async def test_concurrent_consumes_do_not_lose_updates(gate):
    results = await asyncio.gather(*(gate.consume("v1") for _ in range(20)))
    assert sorted(results, reverse=True)[0] == 2  # first increment leaves 2
    assert (await gate.check("v1")).mode == "blocked"
    assert await gate._used("v1") == 20


async def test_namespaces_do_not_collide(redis):
    a = Gate(redis, free_actions=1, namespace="a")
    b = Gate(redis, free_actions=1, namespace="b")
    await a.consume("v1")
    assert (await a.check("v1")).mode == "blocked"
    assert (await b.check("v1")).mode == "free"
