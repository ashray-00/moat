from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
import litellm
from app.config import settings
from app.agent.tools import search_filings, get_financial_fact, compute_growth

TOOLS = [search_filings, get_financial_fact, compute_growth]

async def agent_node(state: MessagesState) -> dict:
    """LLM decides: answer, or call a tool. We bind tools so it can emit tool_calls."""
    resp = await litellm.acompletion(
        model=settings.model_flagship, messages=state["messages"],
        tools=[t.args_schema.model_json_schema() for t in TOOLS], tool_choice="auto")
    return {"messages": [resp.choices[0].message]}

def needs_approval(state: MessagesState) -> str:
    """Route to a human gate if the last answer reads like advice, else finish/act."""
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    content = (getattr(last, "content", "") or "").lower()
    if any(w in content for w in ["you should buy", "you should sell", "i recommend buying"]):
        return "human_review"
    return END

def build_agent():
    g = StateGraph(MessagesState)
    g.add_node("agent", agent_node)
    g.add_node("tools", ToolNode(TOOLS))
    g.add_node("human_review", lambda s: s)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", needs_approval,
                             {"tools": "tools", "human_review": "human_review", END: END})
    g.add_edge("tools", "agent")
    g.add_edge("human_review", END)
    return g.compile(checkpointer=MemorySaver(), interrupt_before=["human_review"])

agent = build_agent()
