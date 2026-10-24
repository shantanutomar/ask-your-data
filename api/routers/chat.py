from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from db import meta
from deps import State, UserKey, VisitorId, pick_llm
from pipeline.orchestrator import ChatDeps, ChatRequest, run_chat
from utils import sse

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None


def _single_error(code: str, message: str) -> StreamingResponse:
    async def gen() -> AsyncIterator[str]:
        yield sse({"type": "error", "code": code, "message": message})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/stream")
async def chat_stream(
    state: State, visitor_id: VisitorId, user_key: UserKey, body: ChatBody
) -> StreamingResponse:
    dataset = await meta.get_active_dataset(state.pool, visitor_id)
    if dataset is None:
        return _single_error(
            "no_dataset", "Load a dataset first (upload a file or use the sample)."
        )

    llm, must_close = pick_llm(state, user_key)
    if llm is None:
        return _single_error(
            "quota_exhausted", "The demo key isn't configured. Enter your own OpenAI API key."
        )

    deps = ChatDeps(
        pool=state.pool, redis=state.redis, settings=state.settings, gate=state.gate, llm=llm
    )
    req = ChatRequest(
        visitor_id=visitor_id,
        has_user_key=user_key is not None,
        question=body.question.strip(),
        conversation_id=body.conversation_id,
        dataset=dataset,
    )

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in run_chat(deps, req):
                yield sse(event)
        finally:
            if must_close:
                await llm.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
