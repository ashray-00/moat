from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import RequiredUser
from app.memory.store import (
    get_session_summary,
    summarize_session,
    upsert_session_summary,
)
from app.safety.guards import MAX_QUERY_LEN, input_ok, sanitize_memory_text

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryMessage(BaseModel):
    role: str
    content: str = Field(max_length=8000)


class UpsertMemoryBody(BaseModel):
    thread_id: str = Field(min_length=1, max_length=128)
    summary: str | None = Field(default=None, max_length=8000)
    messages: list[MemoryMessage] | None = None


@router.get("/{thread_id}")
async def read_memory(thread_id: str, user_id: RequiredUser):
    summary = await get_session_summary(user_id, thread_id)
    return {"thread_id": thread_id, "summary": summary}


@router.put("")
async def write_memory(body: UpsertMemoryBody, user_id: RequiredUser):
    summary = body.summary
    if not summary:
        if not body.messages:
            raise HTTPException(400, "Provide summary or messages to summarize")
        for m in body.messages:
            ok, reason = input_ok(m.content[:MAX_QUERY_LEN])
            if not ok:
                raise HTTPException(400, reason)
        summary = await summarize_session([m.model_dump() for m in body.messages])
    else:
        ok, reason = input_ok(summary[:MAX_QUERY_LEN])
        if not ok:
            raise HTTPException(400, reason)
    summary = sanitize_memory_text(summary)
    await upsert_session_summary(user_id, body.thread_id, summary)
    return {"thread_id": body.thread_id, "summary": summary}
