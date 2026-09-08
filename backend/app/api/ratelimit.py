"""Simple in-process per-key rate limiter. Not shared across workers."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException

from app.config import settings

_hits: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(
    key: str,
    *,
    limit: int | None = None,
    window_seconds: float = 60.0,
) -> None:
    """Enforce a sliding window.

    If ``limit`` is omitted, falls back to ``settings.rate_limit_per_minute``
    (used for anonymous traffic). ``limit <= 0`` disables the check.
    """
    cap = settings.rate_limit_per_minute if limit is None else limit
    if cap <= 0:
        return
    now = time.monotonic()
    window = float(window_seconds)
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= cap:
        raise HTTPException(429, "Rate limit exceeded. Try again shortly.")
    q.append(now)
