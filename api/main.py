from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.types import ASGIApp, Receive, Scope, Send

from config import get_settings
from db import meta
from db.pool import create_pool, run_migrations
from deps import AppState
from fake_llm import FakeLLM
from gate import Gate
from ingest.parsers import CapacityError, IngestError
from llm import LLMError, LLMProtocol, OpenAILLM
from routers import chat, conversations, datasets, key

settings = get_settings()
logging.basicConfig(
    level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # request lines, no need at INFO
logger = logging.getLogger("main")

SWEEP_INTERVAL_SECONDS = 3600


async def _sweep_once(pool) -> None:
    try:
        dropped = await meta.sweep_expired(pool)
        if dropped:
            logger.info("expired datasets dropped: %d", dropped)
    except Exception:
        logger.exception("dataset sweep failed")


async def _sweep_loop(pool) -> None:
    while True:
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
        await _sweep_once(pool)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = await create_pool(settings.database_url)
    await run_migrations(pool)
    redis = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        health_check_interval=30,
    )
    gate = Gate(
        redis,
        free_actions=settings.free_actions,
        namespace=settings.gate_namespace,
        ttl_days=settings.gate_ttl_days,
    )
    server_llm: LLMProtocol | None = None
    if settings.fake_llm:
        logger.warning("FAKE_LLM is enabled: answers are canned. Never set this in production.")
        server_llm = FakeLLM()
    elif settings.openai_api_key:
        server_llm = OpenAILLM(settings.openai_api_key, owns_client=False)
    else:
        logger.warning("OPENAI_API_KEY is not set: only visitors with their own key can chat.")
    app.state.ayd = AppState(
        settings=settings, pool=pool, redis=redis, gate=gate, server_llm=server_llm
    )
    await _sweep_once(pool)  # clear anything that expired while the API was down
    sweeper = asyncio.create_task(_sweep_loop(pool))
    try:
        yield
    finally:
        sweeper.cancel()
        await redis.aclose()
        await pool.close()


class BodyLimitMiddleware:
    """Reject oversized POST bodies by Content-Length before they are read or spooled to disk.

    Pure ASGI (not BaseHTTPMiddleware) so SSE streaming and client-disconnect handling are
    untouched. Chunked uploads without a Content-Length are still bounded by the handlers.
    """

    def __init__(self, app: ASGIApp, limits: dict[str, int]) -> None:
        self.app = app
        self.limits = limits

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST":
            limit = self.limits.get(scope["path"])
            if limit is not None:
                raw = dict(scope["headers"]).get(b"content-length")
                if raw and raw.isdigit() and int(raw) > limit:
                    response = JSONResponse(
                        status_code=413, content={"detail": "The request body is too large."}
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)


docs = {} if settings.enable_docs else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title="ask-your-data", lifespan=lifespan, **docs)

app.add_middleware(
    BodyLimitMiddleware,
    limits={
        "/api/datasets/preview": settings.max_upload_mb * 1024 * 1024 + 64 * 1024,
        "/api/datasets/preview-text": settings.max_free_text_chars * 4 + 1024,
        "/api/datasets/commit": 256 * 1024,
        "/api/chat/stream": 32 * 1024,
    },
)
# Added last so it is outermost: CORS headers also appear on short-circuited 413 responses.
# Auth lives in request headers (visitor id / user API key), not cookies, so wildcard CORS is safe.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],  # includes X-Visitor-Id and X-User-Api-Key
)

app.include_router(datasets.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(key.router)


@app.exception_handler(IngestError)
async def ingest_error_handler(_: Request, exc: IngestError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(CapacityError)
async def capacity_error_handler(_: Request, exc: CapacityError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "The demo is at capacity right now. Please try again later."},
    )


@app.exception_handler(LLMError)
async def llm_error_handler(_: Request, exc: LLMError) -> JSONResponse:
    status = {"quota_exhausted": 402, "invalid_key": 401}.get(exc.code, 502)
    return JSONResponse(status_code=status, content={"code": exc.code, "detail": exc.message})


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness: the process is up (migrations already ran before the server accepts traffic)."""
    return {"status": "ok"}


@app.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    """Readiness: Postgres and Redis both answer."""
    state: AppState = request.app.state.ayd
    try:
        await state.pool.fetchval("SELECT 1")
        await state.redis.ping()
    except Exception:
        logger.exception("readiness check failed")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return JSONResponse(content={"status": "ready"})
