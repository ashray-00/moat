import json
import logging
import time
from typing import Any, AsyncIterator, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel, Field

from app.agent.graph import build_agent, is_advice_like
from app.agent.checkpoint import get_checkpointer, thread_config
from app.agent.pending import create_pending_run, get_pending_run, resolve_pending
from app.api.deps import RequiredUser, get_user_plan
from app.api.limits import finalize_usage, plan_rpm, reserve_quota
from app.api.cost_guards import assert_agent_allowed
from app.api.ratelimit import check_rate_limit
from app.memory.store import load_memory, remember_turn
from app.obs import flush_langfuse, span_set_io, span_update, trace_span
from app.safety.guards import (
    input_ok,
    output_ok,
    sanitize_chat_messages,
    sanitize_memory_text,
    sanitize_memory_turns,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

REWRITE_SYSTEM = (
    "Rewrite the previous assistant draft as research-only. "
    "Do not tell the user to buy, sell, or hold. Do not recommend trades. "
    "Keep citations and filed figures. If tools are needed, call them."
)


class AgentBody(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    thread_id: str = Field(default="research", max_length=128)


class ResumeBody(BaseModel):
    run_id: str = Field(min_length=8, max_length=64)
    action: Literal["approve", "rewrite"]
    thread_id: str = Field(default="research", max_length=128)


def _content_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


def _extract_citations(tool_payload: str) -> list[dict]:
    try:
        data = json.loads(tool_payload)
    except Exception:
        return []
    if not isinstance(data, dict) or not data.get("ok"):
        return []
    out = []
    for ex in data.get("excerpts") or []:
        if not isinstance(ex, dict):
            continue
        cid = ex.get("citation_id") or (
            f"c{ex['chunk_id']}" if ex.get("chunk_id") is not None else None
        )
        if not cid:
            continue
        out.append(
            {
                "id": cid,
                "ticker": ex.get("ticker") or "",
                "section": ex.get("section") or "",
            }
        )
    for block in data.get("results") or []:
        if not isinstance(block, dict):
            continue
        for ex in block.get("excerpts") or []:
            if not isinstance(ex, dict):
                continue
            cid = ex.get("citation_id")
            if cid:
                out.append(
                    {
                        "id": cid,
                        "ticker": ex.get("ticker") or block.get("ticker") or "",
                        "section": ex.get("section") or "",
                    }
                )
    return out


def _extract_series(tool_payload: str) -> dict | None:
    try:
        data = json.loads(tool_payload)
    except Exception:
        return None
    if isinstance(data, dict) and data.get("ok") and data.get("series"):
        return {
            "ticker": data.get("ticker"),
            "metric": data.get("metric"),
            "unit": data.get("unit") or "USD",
            "series": data["series"],
        }
    return None


def _serialize_messages(messages: list) -> list[dict]:
    """Persist a rewrite-capable transcript (OpenAI-ish dicts)."""
    out: list[dict] = []
    for m in messages:
        if isinstance(m, dict):
            role = m.get("role")
            if role in ("system", "user", "assistant", "tool"):
                item = {"role": role, "content": m.get("content") or ""}
                if role == "tool" and m.get("tool_call_id"):
                    item["tool_call_id"] = m["tool_call_id"]
                if role == "assistant" and m.get("tool_calls"):
                    item["tool_calls"] = m["tool_calls"]
                out.append(item)
            continue
        if isinstance(m, AIMessage):
            item = {"role": "assistant", "content": _content_text(m.content)}
            if m.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc.get("id"),
                        "type": "function",
                        "function": {
                            "name": tc.get("name"),
                            "arguments": json.dumps(tc.get("args") or {}),
                        },
                    }
                    for tc in m.tool_calls
                ]
            out.append(item)
        elif isinstance(m, ToolMessage):
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": m.tool_call_id,
                    "content": _content_text(m.content),
                }
            )
        else:
            role = getattr(m, "type", "user")
            role = {"human": "user", "ai": "assistant", "system": "system"}.get(
                role, "user"
            )
            out.append({"role": role, "content": _content_text(getattr(m, "content", ""))})
    return out


@router.post("/run")
async def run_agent(body: AgentBody, user_id: RequiredUser):
    events = []
    async for ev in _agent_events(
        query=body.query,
        thread_id=body.thread_id or "research",
        user_id=user_id,
        seed_messages=None,
        charge_quota=True,
    ):
        events.append(ev)
    final = next((e for e in reversed(events) if e.get("type") == "done"), None)
    if not final:
        err = next((e for e in events if e.get("type") == "error"), None)
        raise HTTPException(
            (err or {}).get("status") or 500,
            (err or {}).get("message") or "agent failed",
        )
    return {
        "status": final.get("status") or "ok",
        "answer": final.get("answer") or "",
        "thread_id": body.thread_id or "research",
        "run_id": final.get("run_id"),
        "sources": final.get("sources") or [],
        "series": final.get("series"),
    }


@router.post("/stream")
async def stream_agent(body: AgentBody, user_id: RequiredUser):
    async def gen():
        async for ev in _agent_events(
            query=body.query,
            thread_id=body.thread_id or "research",
            user_id=user_id,
            seed_messages=None,
            charge_quota=True,
        ):
            yield f"data: {json.dumps(ev)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/resume")
async def resume_agent(body: ResumeBody, user_id: RequiredUser):
    pending = await get_pending_run(body.run_id, user_id)

    if body.action == "approve":
        try:
            await remember_turn(
                user_id,
                pending["thread_id"],
                pending["query"],
                pending["draft_answer"],
            )
        except Exception:
            logger.exception("remember_turn on approve failed")
            raise HTTPException(500, "Could not save approved answer")
        await resolve_pending(body.run_id, user_id, "approved")
        return {
            "status": "ok",
            "answer": pending["draft_answer"],
            "thread_id": pending["thread_id"],
            "run_id": body.run_id,
            "sources": pending["sources"],
            "series": pending["series"],
        }

    # rewrite — stream continuation
    async def gen():
        messages = list(pending["messages"])
        messages.append({"role": "system", "content": REWRITE_SYSTEM})
        messages.append(
            {
                "role": "user",
                "content": (
                    "Please rewrite the last research answer without any "
                    "buy/sell/hold recommendations."
                ),
            }
        )
        await resolve_pending(body.run_id, user_id, "rewritten")
        async for ev in _agent_events(
            query=pending["query"],
            thread_id=pending["thread_id"],
            user_id=user_id,
            seed_messages=messages,
            charge_quota=True,
        ):
            yield f"data: {json.dumps(ev)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


async def _agent_events(
    *,
    query: str,
    thread_id: str,
    user_id: str,
    seed_messages: list[dict] | None,
    charge_quota: bool,
) -> AsyncIterator[dict[str, Any]]:
    if seed_messages is None:
        ok, reason = input_ok(query)
        if not ok:
            yield {"type": "error", "message": reason}
            return

    plan = await get_user_plan(user_id)
    usage_id: int | None = None
    try:
        assert_agent_allowed(plan)
        check_rate_limit(f"agent:{user_id}", limit=plan_rpm(plan))
        if charge_quota:
            usage_id = await reserve_quota(user_id, plan)
    except HTTPException as exc:
        yield {"type": "error", "message": str(exc.detail), "status": exc.status_code}
        return

    if seed_messages is None:
        mem = await load_memory(user_id, thread_id)
        seed: list[dict] = []
        if mem["summary"]:
            seed.append(
                {
                    "role": "system",
                    "content": (
                        "Session memory (prior research focus): "
                        f"{sanitize_memory_text(mem['summary'])}"
                    ),
                }
            )
        seed.extend(sanitize_memory_turns(mem["recent"]))
        seed.append({"role": "user", "content": query})
    else:
        # Rewrite/resume transcript may include tool payloads; preserve structure.
        seed = sanitize_chat_messages(seed_messages)

    with trace_span(
        "agent",
        as_type="agent",
        input={"query": query, "thread_id": thread_id},
        metadata={"plan": plan},
        user_id=user_id,
    ) as root_span:
        async for ev in _agent_events_traced(
            query=query,
            thread_id=thread_id,
            user_id=user_id,
            seed=seed,
            plan=plan,
            usage_id=usage_id,
            charge_quota=charge_quota,
            root_span=root_span,
        ):
            yield ev


async def _agent_events_traced(
    *,
    query: str,
    thread_id: str,
    user_id: str,
    seed: list[dict],
    plan: str,
    usage_id: int | None,
    charge_quota: bool,
    root_span,
) -> AsyncIterator[dict[str, Any]]:
    agent, usage_acc = build_agent(user_id, checkpointer=await get_checkpointer())
    run_config = thread_config(user_id, thread_id)
    sources: list[dict] = []
    series = None
    seen_source_ids: set[str] = set()
    answer = ""
    collected_messages: list = list(seed)
    grounding_ok = True
    run_id = None
    status = "error"
    t0 = time.perf_counter()
    usage_finalized = False

    try:
        try:
            async for event in agent.astream(
                {"messages": seed},
                config=run_config,
                stream_mode="updates",
            ):
                if not isinstance(event, dict):
                    continue
                for node, update in event.items():
                    if not isinstance(update, dict):
                        continue
                    messages = update.get("messages") or []
                    collected_messages.extend(messages)
                    for msg in messages:
                        if isinstance(msg, AIMessage) and getattr(
                            msg, "tool_calls", None
                        ):
                            for tc in msg.tool_calls:
                                yield {
                                    "type": "tool_start",
                                    "name": tc.get("name") or "",
                                    "args": tc.get("args") or {},
                                }
                        if isinstance(msg, ToolMessage):
                            payload = _content_text(msg.content)
                            name = getattr(msg, "name", None) or "tool"
                            yield {
                                "type": "tool_result",
                                "name": name,
                                "ok": '"ok": true' in payload.lower()
                                or '"ok":true' in payload.lower(),
                            }
                            for src in _extract_citations(payload):
                                if src["id"] not in seen_source_ids:
                                    seen_source_ids.add(src["id"])
                                    sources.append(src)
                            maybe_series = _extract_series(payload)
                            if maybe_series:
                                series = maybe_series
                        if (
                            isinstance(msg, AIMessage)
                            and not getattr(msg, "tool_calls", None)
                            and node == "agent"
                        ):
                            answer = _content_text(msg.content)
                            if answer:
                                yield {"type": "answer", "delta": answer}
        except Exception:
            logger.exception("agent failed")
            span_update(root_span, level="ERROR", status_message="agent failed")
            yield {"type": "error", "message": "agent failed"}
            return

        wall_ms = int((time.perf_counter() - t0) * 1000)
        if usage_id is not None:
            try:
                await finalize_usage(
                    usage_id,
                    model=usage_acc.get("model") or "agent",
                    tokens_in=int(usage_acc.get("tokens_in") or 0),
                    tokens_out=int(usage_acc.get("tokens_out") or 0),
                    cached_in=int(usage_acc.get("cached_in") or 0),
                    cost_usd=float(usage_acc.get("cost_usd") or 0),
                    latency_ms=int(usage_acc.get("latency_ms") or wall_ms),
                )
                usage_finalized = True
            except Exception:
                logger.exception("finalize_usage failed user=%s", user_id)

        if sources:
            yield {"type": "sources", "sources": sources}
        if series:
            yield {"type": "series", "series": series}

        if answer and sources:
            grounding_ok, _ = output_ok(answer)
            if not grounding_ok:
                yield {
                    "type": "warning",
                    "code": "ungrounded",
                    "message": "Draft used tools but has no [cite:…] markers.",
                }

        status = "ok"
        if answer and is_advice_like(answer):
            status = "needs_human_review"
            try:
                run_id = await create_pending_run(
                    user_id=user_id,
                    thread_id=thread_id,
                    query=query,
                    draft_answer=answer,
                    messages=_serialize_messages(collected_messages),
                    sources=sources,
                    series=series,
                )
            except Exception:
                logger.exception("create_pending_run failed")
                status = "error"
                yield {
                    "type": "error",
                    "message": "Could not hold answer for review. Try again.",
                }
                return
        elif answer:
            try:
                await remember_turn(user_id, thread_id, query, answer)
            except Exception:
                logger.exception(
                    "remember_turn failed user=%s thread=%s", user_id, thread_id
                )

        done: dict[str, Any] = {
            "type": "done",
            "status": status,
            "answer": answer,
            "sources": sources,
            "series": series,
            "thread_id": thread_id,
            "grounding_ok": grounding_ok,
        }
        if run_id:
            done["run_id"] = run_id
        yield done
        span_update(
            root_span,
            output={
                "status": status,
                "answer_len": len(answer or ""),
                "sources": len(sources),
                "grounding_ok": grounding_ok,
                "cost_usd": usage_acc.get("cost_usd"),
                "tokens_in": usage_acc.get("tokens_in"),
                "tokens_out": usage_acc.get("tokens_out"),
                "run_id": run_id,
            },
        )
        span_set_io(
            root_span,
            input={"query": query, "thread_id": thread_id},
            output={"status": status, "answer_len": len(answer or "")},
        )
    finally:
        if usage_id is not None and not usage_finalized:
            try:
                await finalize_usage(
                    usage_id,
                    model=usage_acc.get("model") or "agent_error",
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                )
            except Exception:
                logger.exception("finalize_usage cleanup failed user=%s", user_id)
        flush_langfuse()
