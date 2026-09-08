import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.graph import agent
from app.api.deps import RequiredUser, get_user_plan
from app.api.limits import enforce_quota, log_usage, plan_rpm
from app.api.ratelimit import check_rate_limit
from app.memory.store import load_memory, remember_turn
from app.safety.guards import input_ok

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentBody(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    thread_id: str = Field(default="research", max_length=128)


@router.post("/run")
async def run_agent(body: AgentBody, user_id: RequiredUser):
    ok, reason = input_ok(body.query)
    if not ok:
        raise HTTPException(400, reason)

    plan = await get_user_plan(user_id)
    check_rate_limit(f"agent:{user_id}", limit=plan_rpm(plan))
    await enforce_quota(user_id, plan)

    thread_id = body.thread_id or "research"
    mem = await load_memory(user_id, thread_id)

    # Durable working + mid-term memory from Postgres; ephemeral graph id per run
    # so tool loops within this request work without duplicating prior turns.
    config = {
        "configurable": {"thread_id": f"{user_id}:{thread_id}:{uuid.uuid4().hex[:8]}"}
    }

    seed: list[dict] = []
    if mem["summary"]:
        seed.append(
            {
                "role": "system",
                "content": f"Session memory (prior research focus): {mem['summary']}",
            }
        )
    seed.extend(mem["recent"])
    seed.append({"role": "user", "content": body.query})

    try:
        result = await agent.ainvoke({"messages": seed}, config=config)
    except Exception as exc:
        raise HTTPException(500, f"agent failed: {exc}") from exc

    state = await agent.aget_state(config)
    interrupted = bool(state.next)

    messages = result.get("messages") or []
    last = messages[-1] if messages else None
    content = getattr(last, "content", None) or (
        last.get("content") if isinstance(last, dict) else ""
    )
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )

    if content:
        try:
            await remember_turn(user_id, thread_id, body.query, str(content))
        except Exception:
            pass

    await log_usage(user_id, model="agent")

    return {
        "status": "needs_human_review" if interrupted else "ok",
        "answer": content,
        "thread_id": thread_id,
    }
