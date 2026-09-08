from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import RequiredUser
from app.memory.store import (
    get_session_summary,
    summarize_session,
    upsert_session_summary,
)

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryMessage(BaseModel):
    role: str
    content: str


class UpsertMemoryBody(BaseModel):
    thread_id: str = Field(min_length=1, max_length=128)
    summary: str | None = None
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
        summary = await summarize_session([m.model_dump() for m in body.messages])
    await upsert_session_summary(user_id, body.thread_id, summary)
    return {"thread_id": body.thread_id, "summary": summary}
