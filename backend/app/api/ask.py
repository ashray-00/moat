import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.answer.engine import answer_stream

router = APIRouter()

class AskBody(BaseModel):
    query: str
    ticker: str | None = None

@router.post("/ask")
async def ask(body: AskBody):
    async def event_gen():
        async for ev in answer_stream(body.query, body.ticker):
            yield f"data: {json.dumps(ev)}\n\n"
    return StreamingResponse(event_gen(), media_type="text/event-stream")