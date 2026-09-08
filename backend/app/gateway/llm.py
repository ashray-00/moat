import time
from dataclasses import dataclass, field
import litellm
from litellm import acompletion
from app.config import settings
from app.gateway.usage import cost_usd, merge_usage, usage_from_response

litellm.drop_params = True

# Re-export for existing imports
__all__ = [
    "LLMResult",
    "complete",
    "route",
    "merge_usage",
    "usage_from_response",
    "cost_usd",
]


@dataclass
class LLMResult:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    cached_in: int
    cost_usd: float
    latency_ms: int
    raw: object = field(repr=False, default=None)


def route(query: str, has_math: bool, n_docs: int) -> str:
    """Cheap tier for simple factual lookups; flagship for multi-doc synthesis/math.
    """
    q = query.lower()
    simple = (any(k in q for k in ["what is.", "revenue", "net income", "eps", "when did"])
              and n_docs <= 3 and not has_math)
    return settings.model_cheap if simple else settings.model_flagship


async def complete(messages: list[dict], model: str | None = None,
                  cache_system: bool = True, max_tokens: int = 1024) -> LLMResult:
    model = model or settings.model_flagship
    if cache_system and messages and messages[0]["role"] == "system" and "anthropic" in model:
        sys = messages[0]
        messages = [{**sys, "content": [
            {"type": "text", "text": sys["content"],
            "cache_control": {"type": "ephemeral"}}]}] + messages[1:]
    t0 = time.perf_counter()
    resp = await acompletion(model=model, messages=messages, max_tokens=max_tokens)
    latency = int((time.perf_counter() - t0) * 1000)
    u = resp.usage
    cached = getattr(u, "cache_read_input_tokens", 0) or 0
    return LLMResult(
        text=resp.choices[0].message.content,
        model=model,
        tokens_in=u.prompt_tokens,
        tokens_out=u.completion_tokens,
        cached_in=cached,
        cost_usd=cost_usd(model, u.prompt_tokens, u.completion_tokens, cached),
        latency_ms=latency,
        raw=resp,
    )
