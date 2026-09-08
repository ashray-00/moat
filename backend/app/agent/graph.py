import json
import time

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
import litellm

from app.agent.tools import AGENT_SYSTEM, make_agent_tools
from app.config import settings
from app.gateway.usage import merge_usage, usage_from_response
from app.safety.guards import is_advice_like

# Re-export for API / tests
__all__ = ["build_agent", "agent", "is_advice_like"]


def _messages_for_litellm(messages: list) -> list[dict]:
    """Normalize LangChain / dict messages into OpenAI chat payloads."""
    out: list[dict] = []
    for m in messages:
        if isinstance(m, dict):
            out.append(m)
            continue
        if isinstance(m, SystemMessage):
            out.append({"role": "system", "content": m.content})
        elif isinstance(m, HumanMessage):
            out.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            item: dict = {"role": "assistant", "content": m.content or ""}
            if m.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
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
                    "content": m.content
                    if isinstance(m.content, str)
                    else json.dumps(m.content),
                }
            )
        elif isinstance(m, BaseMessage):
            role = getattr(m, "type", "user")
            role = {
                "human": "user",
                "ai": "assistant",
                "tool": "tool",
                "system": "system",
            }.get(role, role)
            out.append({"role": role, "content": getattr(m, "content", "") or ""})
        else:
            out.append({"role": "user", "content": str(m)})
    return out


def _to_ai_message(msg) -> AIMessage:
    """Convert a LiteLLM/OpenAI chat message into a LangChain AIMessage."""
    tool_calls = []
    raw_calls = getattr(msg, "tool_calls", None) or []
    for i, tc in enumerate(raw_calls):
        if isinstance(tc, dict):
            fn = tc.get("function") or {}
            args = fn.get("arguments") or tc.get("args") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            tool_calls.append(
                {
                    "id": tc.get("id") or f"call_{i}",
                    "name": fn.get("name") or tc.get("name") or "",
                    "args": args,
                }
            )
        else:
            fn = getattr(tc, "function", None)
            args = getattr(fn, "arguments", "{}") if fn else "{}"
            if isinstance(args, str):
                args = json.loads(args or "{}")
            tool_calls.append(
                {
                    "id": getattr(tc, "id", None) or f"call_{i}",
                    "name": getattr(fn, "name", "") if fn else "",
                    "args": args,
                }
            )

    return AIMessage(
        content=getattr(msg, "content", None) or "",
        tool_calls=tool_calls,
    )


def _route_after_agent(state: MessagesState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END


def build_agent(user_id: str, checkpointer=None):
    """Compile a per-user agent. Returns (compiled_graph, usage_accumulator).

    usage_accumulator is mutated on each LLM call so the API can log real cost.
    Product HITL (Approve/Rewrite) uses pending runs in the API. When
    ``checkpointer`` is set (AsyncPostgresSaver), graph state is durable per
    ``user_id:thread_id``.
    """
    tools = make_agent_tools(user_id)
    openai_tools = [convert_to_openai_tool(t) for t in tools]
    usage_acc: dict = {
        "tokens_in": 0,
        "tokens_out": 0,
        "cached_in": 0,
        "cost_usd": 0.0,
        "model": settings.model_flagship,
        "latency_ms": 0,
    }

    async def agent_node(state: MessagesState) -> dict:
        msgs = _messages_for_litellm(state["messages"])
        if not any(m.get("role") == "system" for m in msgs):
            msgs = [{"role": "system", "content": AGENT_SYSTEM}, *msgs]
        model = settings.model_flagship
        t0 = time.perf_counter()
        resp = await litellm.acompletion(
            model=model,
            messages=msgs,
            tools=openai_tools,
            tool_choice="auto",
        )
        latency = int((time.perf_counter() - t0) * 1000)
        piece = usage_from_response(resp, model)
        merge_usage(usage_acc, piece)
        usage_acc["latency_ms"] = int(usage_acc.get("latency_ms") or 0) + latency
        return {"messages": [_to_ai_message(resp.choices[0].message)]}

    g = StateGraph(MessagesState)
    g.add_node("agent", agent_node)
    g.add_node("tools", ToolNode(tools))
    g.add_edge(START, "agent")
    g.add_conditional_edges(
        "agent",
        _route_after_agent,
        {"tools": "tools", END: END},
    )
    g.add_edge("tools", "agent")
    compiled = g.compile(checkpointer=checkpointer) if checkpointer else g.compile()
    return compiled, usage_acc


_default_graph, _ = build_agent("system")
agent = _default_graph