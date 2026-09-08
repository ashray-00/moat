import json
import logging
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.answer.engine import answer_stream
from app.api.deps import OptionalUser, get_user_plan
from app.api.limits import enforce_quota, log_usage, plan_rpm
from app.api.ratelimit import check_rate_limit
from app.config import settings
from app.gateway.cache import get_cached
from app.memory.store import load_memory, remember_turn
from app.obs import langfuse
from app.safety.guards import input_ok

logger = logging.getLogger(__name__)
router = APIRouter()


class AskBody(BaseModel):
    query: str
    ticker: str | None = None
    thread_id: str | None = None


@router.post("/ask")
async def ask(body: AskBody, user_id: OptionalUser):
    ok, reason = input_ok(body.query)
    if not ok:
        raise HTTPException(400, reason)

    if user_id:
        plan = await get_user_plan(user_id)
        check_rate_limit(user_id, limit=plan_rpm(plan))
        await enforce_quota(user_id, plan)
    else:
        check_rate_limit("anonymous")

    if langfuse is not None:
        try:
            langfuse.update_current_trace(
                inputs={"query": body.query, "ticker": body.ticker, "user_id": user_id},
                tags=["ask"],
                user_id=user_id,
            )
        except Exception:
            pass

    thread_id = body.thread_id or "research"
    session_summary = None
    prior_turns: list[dict] = []
    if user_id:
        mem = await load_memory(user_id, thread_id)
        session_summary = mem["summary"]
        prior_turns = mem["recent"]

    if settings.answer_cache_enabled:
        cached = await get_cached(body.query)
        if cached:

            async def cached_gen():
                yield f"data: {json.dumps({'type': 'answer', 'delta': cached})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                if user_id:
                    await log_usage(user_id, model="cache", latency_ms=0)

            return StreamingResponse(cached_gen(), media_type="text/event-stream")

    started = time.perf_counter()

    async def event_gen():
        answer_text = ""
        model_used = ""
        tokens_in = tokens_out = cached_in = 0
        cost_usd = 0.0
        try:
            async for ev in answer_stream(
                body.query,
                body.ticker,
                session_summary=session_summary,
                prior_turns=prior_turns,
            ):
                if ev.get("type") == "answer":
                    answer_text += ev.get("delta", "")
                if ev.get("type") == "meta":
                    if ev.get("model"):
                        model_used = ev["model"]
                    if "tokens_in" in ev:
                        tokens_in = int(ev.get("tokens_in") or 0)
                        tokens_out = int(ev.get("tokens_out") or 0)
                        cached_in = int(ev.get("cached_in") or 0)
                        cost_usd = float(ev.get("cost_usd") or 0)
                    continue
                yield f"data: {json.dumps(ev)}\n\n"
            if user_id and answer_text:
                try:
                    await remember_turn(user_id, thread_id, body.query, answer_text)
                except Exception:
                    logger.exception(
                        "remember_turn failed user=%s thread=%s", user_id, thread_id
                    )
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc) or 'ask failed'})}\n\n"
            return
        finally:
            if user_id:
                latency_ms = int((time.perf_counter() - started) * 1000)
                try:
                    await log_usage(
                        user_id,
                        model=model_used,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        cached_in=cached_in,
                        cost_usd=cost_usd,
                        latency_ms=latency_ms,
                    )
                except Exception:
                    logger.exception("log_usage failed user=%s", user_id)
            if langfuse is not None:
                try:
                    langfuse.update_current_trace(
                        outputs={
                            "answer_len": len(answer_text),
                            "tokens_in": tokens_in,
                            "tokens_out": tokens_out,
                            "cost_usd": cost_usd,
                        }
                    )
                except Exception:
                    logger.debug("langfuse update failed", exc_info=True)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
