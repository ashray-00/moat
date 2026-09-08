"""Default covered ticker universe — shared by seed worker and universe API."""

from __future__ import annotations

_FALLBACK = [
    "AAPL",
    "MSFT",
    "NVDA",
    "GOOGL",
    "AMZN",
    "META",
    "TSLA",
    "AMD",
    "INTC",
    "JPM",
]


def default_universe() -> list[str]:
    """Resolved default list (env MOAT_DEFAULT_UNIVERSE overrides builtin)."""
    from app.config import settings

    raw = (settings.moat_default_universe or "").strip()
    if not raw:
        return list(_FALLBACK)
    out: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        t = part.strip().upper()
        if t and t.isalnum() and t not in seen:
            seen.add(t)
            out.append(t)
    return out or list(_FALLBACK)


# Back-compat: import sites that expect a list constant.
DEFAULT_UNIVERSE: list[str] = list(_FALLBACK)


def is_default_ticker(ticker: str) -> bool:
    return ticker.strip().upper() in set(default_universe())
