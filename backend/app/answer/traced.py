from app.obs import langfuse, observe
from app.answer.engine import answer_stream

@observe(name="answer")
async def answer_traced(query: str, ticker: str | None = None) -> str:
    """Traced answer stream."""
    if langfuse is not None:
        langfuse.update_current_trace(
            inputs={"query": query, "ticker": ticker}, tags=["ask"])
    text, source_ids = "", set()
    async for ev in answer_stream(query, ticker):
        if ev["type"] == "answer":
            text += ev["delta"]
        elif ev["type"] == "sources":
            source_ids = {s["id"] for s in ev["sources"]}
    if langfuse is not None:
        langfuse.update_current_trace(
            outputs={"answer": text, "sources": list(source_ids)})
    return text