"""Sliding-window rate limiter. Uses Redis when REDIS_URL is set, else memory."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException

from app.config import settings

_hits: dict[str, deque[float]] = defaultdict(deque)
_redis = None
_redis_failed = False


def _get_redis():
    global _redis, _redis_failed
    if _redis_failed or not (settings.redis_url or "").strip():
        return None
    if _redis is not None:
        return _redis
    try:
        import redis  # type: ignore

        _redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        _redis.ping()
        return _redis
    except Exception:
        _redis_failed = True
        _redis = None
        return None


def _check_memory(key: str, *, cap: int, window: float) -> None:
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= cap:
        raise HTTPException(429, "Rate limit exceeded. Try again shortly.")
    q.append(now)


def _check_redis(key: str, *, cap: int, window: float) -> None:
    r = _get_redis()
    if r is None:
        _check_memory(key, cap=cap, window=window)
        return
    now = time.time()
    pipe_key = f"moat:rl:{key}"
    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(pipe_key, 0, now - window)
        pipe.zcard(pipe_key)
        pipe.zadd(pipe_key, {f"{now}": now})
        pipe.expire(pipe_key, int(window) + 5)
        results = pipe.execute()
        count = int(results[1])
        if count >= cap:
            # Undo the add we just made when over cap.
            r.zrem(pipe_key, f"{now}")
            raise HTTPException(429, "Rate limit exceeded. Try again shortly.")
    except HTTPException:
        raise
    except Exception:
        _check_memory(key, cap=cap, window=window)


def check_rate_limit(
    key: str,
    *,
    limit: int | None = None,
    window_seconds: float = 60.0,
) -> None:
    """Enforce a sliding window.

    If ``limit`` is omitted, falls back to ``settings.rate_limit_per_minute``.
    ``limit <= 0`` disables the check.
    """
    cap = settings.rate_limit_per_minute if limit is None else limit
    if cap <= 0:
        return
    window = float(window_seconds)
    if (settings.redis_url or "").strip():
        _check_redis(key, cap=cap, window=window)
    else:
        _check_memory(key, cap=cap, window=window)
