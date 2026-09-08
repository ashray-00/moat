import json

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
import litellm

from app.agent.tools import compute_growth, get_financial_fact, search_filings
from app.config import settings

TOOLS = [search_filings, get_financial_fact, compute_growth]
OPENAI_TOOLS = [convert_to_openai_tool(t) for t in TOOLS]


def _messages_for_litellm(messages: list) -> list[dict]:
    """Normalize LangChain / dict messages into OpenAI chat payloads."""
    out: list[dict] = []
    for m in messages:
        if isinstance(m, dict):
            out.append(m)
            continue
        if isinstance(m, HumanMessage):
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
                    "content": m.content if isinstance(m.content, str) else json.dumps(m.content),
                }
            )
        elif isinstance(m, BaseMessage):
            role = getattr(m, "type", "user")
            role = {"human": "user", "ai": "assistant", "tool": "tool"}.get(role, role)
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


async def agent_node(state: MessagesState) -> dict:
    """LLM decides: answer, or call a tool. Tools use OpenAI function format."""
    resp = await litellm.acompletion(
        model=settings.model_flagship,
        messages=_messages_for_litellm(state["messages"]),
        tools=OPENAI_TOOLS,
        tool_choice="auto",
    )
    return {"messages": [_to_ai_message(resp.choices[0].message)]}


def needs_approval(state: MessagesState) -> str:
    """Route to a human gate if the last answer reads like advice, else finish/act."""
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", None)
    if tool_calls:
        return "tools"
    content = (getattr(last, "content", "") or "").lower()
    if any(
        w in content
        for w in ["you should buy", "you should sell", "i recommend buying"]
    ):
        return "human_review"
    return END


def build_agent():
    g = StateGraph(MessagesState)
    g.add_node("agent", agent_node)
    g.add_node("tools", ToolNode(TOOLS))
    g.add_node("human_review", lambda s: s)
    g.add_edge(START, "agent")
    g.add_conditional_edges(
        "agent",
        needs_approval,
        {"tools": "tools", "human_review": "human_review", END: END},
    )
    g.add_edge("tools", "agent")
    g.add_edge("human_review", END)
    return g.compile(checkpointer=MemorySaver(), interrupt_before=["human_review"])


agent = build_agent()
