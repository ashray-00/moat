import litellm

from app.answer.prompts import ANSWER_SYSYTEM, build_context
from app.gateway.llm import route
from app.retrieval.rerank import retrieve
from app.safety.guards import advice_disclaimer_needed, output_ok


async def answer_stream(
    query: str,
    ticker: str | None = None,
    session_summary: str | None = None,
    prior_turns: list[dict] | None = None,
):
    """Async generator yielding answer tokens. Retrieval first, then streamed generation."""
    chunks = await retrieve(query, ticker, top_k=5)
    if not chunks:
        yield {
            "type": "answer",
            "delta": (
                "I don't have filings that cover that. "
                "Try a company in the covered universe."
            ),
        }
        yield {"type": "done"}
        return

    context = build_context(chunks)
    system = ANSWER_SYSYTEM.format(context=context)
    if session_summary:
        system += (
            "\n\n<session_memory>\n"
            f"{session_summary}\n"
            "</session_memory>\n"
        )

    messages: list[dict] = [{"role": "system", "content": system}]
    for turn in prior_turns or []:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": query})

    model = route(query, has_math=False, n_docs=len(chunks))
    yield {"type": "meta", "model": model}

    yield {
        "type": "sources",
        "sources": [
            {"id": f"c{c['id']}", "ticker": c["ticker"], "section": c["section"]}
            for c in chunks
        ],
    }

    answer = ""
    stream = await litellm.acompletion(
        model=model, messages=messages, max_tokens=1024, stream=True
    )
    async for part in stream:
        delta = part.choices[0].delta.content
        if delta:
            answer += delta
            yield {"type": "answer", "delta": delta}

    grounded, _ = output_ok(answer)
    if not grounded and answer:
        note = (
            "\n\nNote: this draft lacked citation markers; treat claims as unverified "
            "until grounded in the sources above."
        )
        yield {"type": "answer", "delta": note}

    if advice_disclaimer_needed(query):
        yield {
            "type": "answer",
            "delta": "\n\nThis is research, not investment advice.",
        }

    yield {"type": "done"}
