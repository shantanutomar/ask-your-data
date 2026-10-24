from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from db import meta
from deps import State, VisitorId

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(state: State, visitor_id: VisitorId) -> dict[str, Any]:
    dataset = await meta.get_active_dataset(state.pool, visitor_id)
    if dataset is None:
        return {"conversations": []}
    return {"conversations": await meta.list_conversations(state.pool, dataset["id"])}


@router.get("/{conversation_id}/messages")
async def conversation_messages(
    conversation_id: str, state: State, visitor_id: VisitorId
) -> dict[str, Any]:
    dataset = await meta.get_active_dataset(state.pool, visitor_id)
    if (
        dataset is None
        or await meta.get_conversation(state.pool, conversation_id, dataset["id"]) is None
    ):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"messages": await meta.list_messages(state.pool, conversation_id)}


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str, state: State, visitor_id: VisitorId
) -> dict[str, bool]:
    dataset = await meta.get_active_dataset(state.pool, visitor_id)
    if dataset is not None:
        await meta.delete_conversation(state.pool, conversation_id, dataset["id"])
    return {"deleted": True}
