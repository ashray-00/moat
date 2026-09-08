import json
import logging
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.answer.engine import answer_stream
from app.api.deps import RequiredUser, get_user_plan
from app.api.limits import finalize_usage, plan_rpm, reserve_quota
from app.api.ratelimit import check_rate_limit
from app.config import settings
from app.gateway.cache import get_cached
from app.memory.store import load_memory, remember_turn
from app.obs import flush_langfuse, span_set_io, span_update, trace_span
from app.safety.guards import input_ok

logger = logging.getLogger(__name__)
router = APIRouter()


class AskBody(BaseModel):
    query: str
    ticker: str | None = None
    thread_id: str | None = None


@router.post("/ask")
async def ask(body: AskBody, user_id: RequiredUser):
    ok, reason = input_ok(body.query)
    if not ok:
        raise HTTPException(400, reason)

    plan = await get_user_plan(user_id)
    check_rate_limit(user_id, limit=plan_rpm(plan))
    usage_id = await reserve_quota(user_id, plan)

    thread_id = body.thread_id or "research"
    mem = await load_memory(user_id, thread_id)
    session_summary = mem["summary"]
    prior_turns = mem["recent"]

    if settings.answer_cache_enabled:
        cached = await get_cached(body.query, user_id=user_id)
        if cached:

            async def cached_gen():
                with trace_span(
                    "ask",
                    as_type="chain",
                    input={
                        "query": body.query,
                        "ticker": body.ticker,
                        "cache": True,
                    },
                    metadata={"plan": plan, "thread_id": thread_id},
                    user_id=user_id,
                ) as span:
                    try:
                        yield f"data: {json.dumps({'type': 'answer', 'delta': cached})}\n\n"
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        span_set_io(
                            span,
                            input={"query": body.query, "ticker": body.ticker},
                            output={"cache_hit": True, "answer_len": len(cached)},
                        )
                    finally:
                        try:
                            await finalize_usage(
                                usage_id, model="cache", latency_ms=0
                            )
                        except Exception:
                            logger.exception(
                                "finalize_usage failed user=%s", user_id
                            )
                        flush_langfuse()

            return StreamingResponse(cached_gen(), media_type="text/event-stream")

    started = time.perf_counter()

    async def event_gen():
        answer_text = ""
        model_used = ""
        tokens_in = tokens_out = cached_in = 0
        cost_usd = 0.0
        with trace_span(
            "ask",
            as_type="chain",
            input={"query": body.query, "ticker": body.ticker},
            metadata={"plan": plan, "thread_id": thread_id},
            user_id=user_id,
        ) as span:
            try:
                async for ev in answer_stream(
                    body.query,
                    body.ticker,
                    session_summary=session_summary,
                    prior_turns=prior_turns,
                    user_id=user_id,
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
                if answer_text:
                    try:
                        await remember_turn(
                            user_id, thread_id, body.query, answer_text
                        )
                    except Exception:
                        logger.exception(
                            "remember_turn failed user=%s thread=%s",
                            user_id,
                            thread_id,
                        )
                span_update(
                    span,
                    output={
                        "answer_len": len(answer_text),
                        "model": model_used,
                        "tokens_in": tokens_in,
                        "tokens_out": tokens_out,
                        "cached_in": cached_in,
                        "cost_usd": cost_usd,
                    },
                    metadata={
                        "user_id": user_id,
                        "plan": plan,
                        "thread_id": thread_id,
                    },
                )
                span_set_io(
                    span,
                    input={"query": body.query, "ticker": body.ticker},
                    output={"answer_len": len(answer_text), "model": model_used},
                )
            except Exception:
                logger.exception("ask stream failed user=%s", user_id)
                span_update(span, level="ERROR", status_message="ask failed")
                yield f"data: {json.dumps({'type': 'error', 'message': 'ask failed'})}\n\n"
                return
            finally:
                latency_ms = int((time.perf_counter() - started) * 1000)
                try:
                    await finalize_usage(
                        usage_id,
                        model=model_used,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        cached_in=cached_in,
                        cost_usd=cost_usd,
                        latency_ms=latency_ms,
                    )
                except Exception:
                    logger.exception("finalize_usage failed user=%s", user_id)
                flush_langfuse()

    return StreamingResponse(event_gen(), media_type="text/event-stream")
