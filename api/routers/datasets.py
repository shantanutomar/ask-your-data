from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from db import meta
from deps import State, UserKey, VisitorId, pick_llm
from ingest import drafts
from ingest.commit import CommitRequest, apply_edits, create_dataset
from ingest.free_text import extract_tables
from ingest.parsers import IngestError, parse_file
from ingest.samples import SAMPLE_NAME, load_sample_tables

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def dataset_summary(dataset: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": dataset["id"],
        "name": dataset["name"],
        "expires_at": dataset["expires_at"].isoformat(),
        "tables": [
            {
                "name": t["name"],
                "row_count": t["row_count"],
                "columns": [{"name": c["name"], "type": c["type"]} for c in t["columns"]],
            }
            for t in dataset["tables"]
        ],
    }


@router.get("/current")
async def current_dataset(state: State, visitor_id: VisitorId) -> dict[str, Any]:
    dataset = await meta.get_active_dataset(state.pool, visitor_id)
    return {"dataset": dataset_summary(dataset) if dataset else None}


@router.delete("/current")
async def reset_dataset(state: State, visitor_id: VisitorId) -> dict[str, bool]:
    return {"deleted": await meta.delete_dataset(state.pool, visitor_id)}


@router.post("/preview")
async def preview_file(
    state: State, visitor_id: VisitorId, file: UploadFile = File(...)
) -> dict[str, Any]:
    settings = state.settings
    limit = settings.max_upload_mb * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise IngestError(f"File is too large; the limit is {settings.max_upload_mb} MB.")
    filename = file.filename or "data"

    def build() -> drafts.Draft:
        raw = parse_file(filename, content, settings.max_total_rows)
        return drafts.build_draft(
            raw, visitor_id=visitor_id, dataset_name=_dataset_name(filename), settings=settings
        )

    draft = await run_in_threadpool(build)
    draft_id = await drafts.save_draft(state.redis, settings.gate_namespace, draft)
    return drafts.draft_preview(draft_id, draft)


def _dataset_name(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0].strip()
    return stem or "My data"


class TextBody(BaseModel):
    text: str = Field(min_length=1)


@router.post("/preview-text")
async def preview_text(
    state: State, visitor_id: VisitorId, user_key: UserKey, body: TextBody
) -> Any:
    """Free-text ingestion: one LLM call, counted as one gate action."""
    settings = state.settings
    if len(body.text) > settings.max_free_text_chars:
        raise IngestError(
            f"Text is too long; the limit is {settings.max_free_text_chars} characters."
        )
    status = await state.gate.check(visitor_id, user_key)
    if status.mode == "blocked":
        return JSONResponse(
            status_code=402,
            content={
                "code": "blocked",
                "detail": "You've used your free tries. Enter your own OpenAI API key to continue.",
            },
        )
    llm, must_close = pick_llm(state, user_key)
    if llm is None:
        return JSONResponse(
            status_code=402,
            content={
                "code": "quota_exhausted",
                "detail": "The demo key isn't configured. Enter your own OpenAI API key.",
            },
        )
    try:
        raw = await extract_tables(llm, settings.model_fast, body.text)
    finally:
        if must_close:
            await llm.aclose()
    draft = await run_in_threadpool(
        lambda: drafts.build_draft(
            raw, visitor_id=visitor_id, dataset_name="Pasted data", settings=settings
        )
    )
    draft_id = await drafts.save_draft(state.redis, settings.gate_namespace, draft)
    if status.mode == "free":
        await state.gate.consume(visitor_id)
    return drafts.draft_preview(draft_id, draft)


@router.post("/commit")
async def commit_draft(state: State, visitor_id: VisitorId, body: CommitRequest) -> dict[str, Any]:
    settings = state.settings
    draft = await drafts.load_draft(state.redis, settings.gate_namespace, body.draft_id, visitor_id)
    tables = await run_in_threadpool(apply_edits, draft, body.tables, settings)
    name = (body.dataset_name or draft.name).strip()[:80] or "My data"
    dataset = await create_dataset(
        state.pool, visitor_id=visitor_id, dataset_name=name, tables=tables, settings=settings
    )
    await drafts.delete_draft(state.redis, settings.gate_namespace, body.draft_id)
    return {"dataset": dataset_summary(dataset)}


@router.post("/sample")
async def load_sample(state: State, visitor_id: VisitorId) -> dict[str, Any]:
    """Bundled synthetic dataset: no AI call, not gated."""
    settings = state.settings

    def build():
        raw = load_sample_tables(settings.max_total_rows)
        draft = drafts.build_draft(
            raw, visitor_id=visitor_id, dataset_name=SAMPLE_NAME, settings=settings
        )
        return apply_edits(draft, None, settings)

    tables = await run_in_threadpool(build)
    dataset = await create_dataset(
        state.pool,
        visitor_id=visitor_id,
        dataset_name=SAMPLE_NAME,
        tables=tables,
        settings=settings,
    )
    return {"dataset": dataset_summary(dataset)}
