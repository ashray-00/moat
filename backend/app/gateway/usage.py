"""Token/cost accounting shared by Ask LLM gateway and the agent graph.

Kept free of LiteLLM imports so offline eval gates stay lightweight.
"""

from __future__ import annotations

from app.config import settings

PRICES = {
    settings.model_flagship: {"in": 2.50, "out": 10.00, "cache_read": 1.25},
    settings.model_cheap: {"in": 0.05, "out": 0.08, "cache_read": 0.0},
}


def cost_usd(model: str, tin: int, tout: int, cached: int = 0) -> float:
    p = PRICES.get(model, {"in": 0.0, "out": 0.0, "cache_read": 0.0})
    fresh = max(0, tin - cached)
    return (fresh * p["in"] + cached * p["cache_read"] + tout * p["out"]) / 1_000_000


def usage_from_response(resp, model: str) -> dict:
    """Normalize LiteLLM/OpenAI usage into Moat usage_log fields."""
    u = getattr(resp, "usage", None)
    if u is None:
        return {
            "tokens_in": 0,
            "tokens_out": 0,
            "cached_in": 0,
            "cost_usd": 0.0,
            "model": model,
        }
    tin = int(getattr(u, "prompt_tokens", 0) or 0)
    tout = int(getattr(u, "completion_tokens", 0) or 0)
    cached = int(getattr(u, "cache_read_input_tokens", 0) or 0)
    return {
        "tokens_in": tin,
        "tokens_out": tout,
        "cached_in": cached,
        "cost_usd": cost_usd(model, tin, tout, cached),
        "model": model,
    }


def merge_usage(into: dict, piece: dict) -> dict:
    into["tokens_in"] = int(into.get("tokens_in") or 0) + int(piece.get("tokens_in") or 0)
    into["tokens_out"] = int(into.get("tokens_out") or 0) + int(
        piece.get("tokens_out") or 0
    )
    into["cached_in"] = int(into.get("cached_in") or 0) + int(piece.get("cached_in") or 0)
    into["cost_usd"] = float(into.get("cost_usd") or 0) + float(
        piece.get("cost_usd") or 0
    )
    into["model"] = piece.get("model") or into.get("model") or ""
    return into
