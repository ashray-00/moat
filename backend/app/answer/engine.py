import litellm
from app.config import settings
from app.answer.prompts import ANSWER_SYSYTEM, build_context
from app.gateway.llm import route
from app.retrieval.rerank import retrieve

async def answer_stream(query: str, ticker: str | None = None):
    """Async generator yielding answer tokens. Retrieval first, then streamied generation."""
    chunks = await retrieve(query, ticker, top_k=5)
    if not chunks:
        yield {"type": "answer", "delta": "I don't have filings that cover that. "
               "Try a company in the covered universe."}
        return
    context = build_context(chunks)
    message = [
        {"role": "system", "content": ANSWER_SYSYTEM.format(context=context)},
        {"role": "user", "content": query}
    ]
    model = route(query, has_math=False, n_docs=len(chunks))

    yield {"type": "sources", "sources": [
        {"id": f"c{c['id']}", "ticker": c["ticker"], "section": c["section"]}
        for c in chunks
    ]}

    stream = await litellm.acompletion(model=model, messages=message,
                                       max_tokens=1024, stream=True)
    async for part in stream:
        delta = part.choices[0].delta.content
        if delta:
            yield {"type": "answer", "delta": delta}

    yield {"type": "done"}