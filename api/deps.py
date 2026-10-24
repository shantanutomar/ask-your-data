"""FastAPI dependencies and shared app-state accessors."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated

import asyncpg
from fastapi import Depends, Header, HTTPException, Request
from redis.asyncio import Redis

from config import Settings
from gate import Gate
from llm import LLMProtocol, OpenAILLM

_VISITOR_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


@dataclass
class AppState:
    settings: Settings
    pool: asyncpg.Pool
    redis: Redis
    gate: Gate
    server_llm: LLMProtocol | None


def get_state(request: Request) -> AppState:
    return request.app.state.ayd


State = Annotated[AppState, Depends(get_state)]


def get_visitor_id(x_visitor_id: Annotated[str | None, Header()] = None) -> str:
    if not x_visitor_id or not _VISITOR_RE.match(x_visitor_id):
        raise HTTPException(status_code=400, detail="Missing or invalid X-Visitor-Id header.")
    return x_visitor_id


def get_user_key(x_user_api_key: Annotated[str | None, Header()] = None) -> str | None:
    key = (x_user_api_key or "").strip()
    return key or None


VisitorId = Annotated[str, Depends(get_visitor_id)]
UserKey = Annotated[str | None, Depends(get_user_key)]


def pick_llm(state: AppState, user_key: str | None) -> tuple[LLMProtocol | None, bool]:
    """Return (llm, must_close). A user key gets its own client; the server client is shared."""
    if user_key:
        return OpenAILLM(user_key), True
    return state.server_llm, False
