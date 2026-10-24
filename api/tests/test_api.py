"""HTTP-level checks of the guards added around the pipeline (no LLM involved)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from config import get_settings
from db import meta

VISITOR = {"X-Visitor-Id": "test-visitor-" + uuid.uuid4().hex}


@pytest.fixture
def client():
    from main import app

    with TestClient(app) as c:
        yield c
        c.delete("/api/datasets/current", headers=VISITOR)


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}


def test_visitor_header_is_required(client):
    assert client.get("/api/datasets/current").status_code == 400
    assert client.get("/api/datasets/current", headers={"X-Visitor-Id": "short"}).status_code == 400


def test_docs_are_disabled_by_default(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_cors_allows_custom_headers(client):
    res = client.options(
        "/api/chat/stream",
        headers={
            "Origin": "https://example.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-visitor-id,x-user-api-key,content-type",
        },
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "*"
    allowed = res.headers["access-control-allow-headers"].lower()
    assert "x-visitor-id" in allowed and "x-user-api-key" in allowed


def test_oversized_body_is_rejected_with_cors_headers(client):
    too_big = (get_settings().max_upload_mb + 2) * 1024 * 1024
    res = client.post(
        "/api/datasets/preview",
        headers={**VISITOR, "Content-Length": str(too_big), "Origin": "https://x.app"},
        content=b"x",
    )
    assert res.status_code == 413
    assert res.headers["access-control-allow-origin"] == "*"


def test_sample_commit_reset_roundtrip_and_validation(client):
    res = client.post("/api/datasets/sample", headers=VISITOR)
    assert res.status_code == 200
    names = [t["name"] for t in res.json()["dataset"]["tables"]]
    assert names == ["customers", "products", "orders", "order_items"]

    csv = b"name,qty\nfoo,1\nbar,2\n"
    prev = client.post("/api/datasets/preview", headers=VISITOR, files={"file": ("t.csv", csv)})
    assert prev.status_code == 200
    assert (
        client.post(
            "/api/datasets/preview", headers=VISITOR, files={"file": ("t.exe", csv)}
        ).status_code
        == 422
    )

    done = client.post(
        "/api/datasets/commit",
        headers=VISITOR,
        json={"draft_id": prev.json()["draft_id"]},
    )
    assert done.status_code == 200
    assert [t["name"] for t in done.json()["dataset"]["tables"]] == ["t"]
    # a draft can only be committed once
    again = client.post(
        "/api/datasets/commit", headers=VISITOR, json={"draft_id": prev.json()["draft_id"]}
    )
    assert again.status_code == 422

    assert client.delete("/api/datasets/current", headers=VISITOR).json() == {"deleted": True}
    assert client.get("/api/datasets/current", headers=VISITOR).json() == {"dataset": None}


def test_dataset_cap_returns_503(client, monkeypatch):
    async def full(*_a, **_k):
        return 10_000

    monkeypatch.setattr(meta, "count_active_datasets", full)
    res = client.post("/api/datasets/sample", headers=VISITOR)
    assert res.status_code == 503


def test_chat_without_dataset_streams_error_event(client):
    res = client.post("/api/chat/stream", headers=VISITOR, json={"question": "hi"})
    assert res.status_code == 200
    assert '"code": "no_dataset"' in res.text


async def test_startup_sweep_drops_expired_datasets(pool, sample_dataset):
    await pool.execute(
        "UPDATE app.datasets SET expires_at = now() - interval '1 minute' WHERE id = $1",
        sample_dataset["id"],
    )
    assert await meta.sweep_expired(pool) >= 1
    exists = await pool.fetchval(
        "SELECT count(*) FROM pg_namespace WHERE nspname = $1", sample_dataset["schema_name"]
    )
    assert exists == 0
