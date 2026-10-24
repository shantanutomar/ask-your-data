from __future__ import annotations

from fastapi import APIRouter, HTTPException

from deps import State, UserKey, VisitorId
from llm import OpenAILLM

router = APIRouter(prefix="/api", tags=["key"])


@router.post("/key/validate")
async def validate_key(user_key: UserKey) -> dict[str, bool]:
    """One cheap `models.list` call. The key is used for this request only."""
    if not user_key:
        raise HTTPException(status_code=400, detail="Missing X-User-Api-Key header.")
    llm = OpenAILLM(user_key)
    try:
        return {"valid": await llm.validate_key()}
    finally:
        await llm.aclose()


@router.get("/gate")
async def gate_status(state: State, visitor_id: VisitorId, user_key: UserKey) -> dict:
    status = await state.gate.check(visitor_id, user_key)
    return {
        "mode": status.mode,
        "remaining": status.remaining,
        "free_actions": state.settings.free_actions,
    }
