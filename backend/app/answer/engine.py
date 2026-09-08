import litellm

from app.answer.prompts import ANSWER_SYSYTEM, build_context
from app.gateway.llm import route
from app.gateway.usage import cost_usd
from app.retrieval.rerank import retrieve
from app.safety.guards import (
    advice_disclaimer_needed,
    output_ok,
    sanitize_memory_text,
    sanitize_memory_turns,
)


def _usage_from_stream_chunk(part, model: str) -> dict | None:
    """Pull usage from a streaming chunk when the provider includes it."""
    u = getattr(part, "usage", None)
    if u is None and isinstance(part, dict):
        u = part.get("usage")
    if u is None:
        return None
    tin = int(getattr(u, "prompt_tokens", None) or getattr(u, "input_tokens", 0) or 0)
    tout = int(
        getattr(u, "completion_tokens", None) or getattr(u, "output_tokens", 0) or 0
    )
    if hasattr(u, "get") and callable(u.get):
        tin = int(u.get("prompt_tokens") or u.get("input_tokens") or tin or 0)
        tout = int(u.get("completion_tokens") or u.get("output_tokens") or tout or 0)
    cached = int(getattr(u, "cache_read_input_tokens", 0) or 0)
    return {
        "tokens_in": tin,
        "tokens_out": tout,
        "cached_in": cached,
        "cost_usd": cost_usd(model, tin, tout, cached),
        "model": model,
    }


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
        safe_summary = sanitize_memory_text(session_summary)
        system += (
            "\n\n<session_memory>\n"
            f"{safe_summary}\n"
            "</session_memory>\n"
        )

    messages: list[dict] = [{"role": "system", "content": system}]
    for turn in sanitize_memory_turns(prior_turns):
        messages.append(turn)
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
    usage_piece: dict | None = None
    kwargs = {"model": model, "messages": messages, "max_tokens": 1024, "stream": True}
    try:
        stream = await litellm.acompletion(
            **kwargs, stream_options={"include_usage": True}
        )
    except TypeError:
        # Older/provider path without stream_options support.
        stream = await litellm.acompletion(**kwargs)

    async for part in stream:
        maybe = _usage_from_stream_chunk(part, model)
        if maybe:
            usage_piece = maybe
        try:
            delta = part.choices[0].delta.content
        except Exception:
            delta = None
        if delta:
            answer += delta
            yield {"type": "answer", "delta": delta}

    if usage_piece:
        yield {
            "type": "meta",
            "model": model,
            "tokens_in": usage_piece["tokens_in"],
            "tokens_out": usage_piece["tokens_out"],
            "cached_in": usage_piece["cached_in"],
            "cost_usd": usage_piece["cost_usd"],
        }

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
