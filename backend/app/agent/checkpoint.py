"""LangGraph AsyncPostgresSaver for durable agent thread state."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_pool: Any = None
_saver: Any = None
_setup_done = False


def checkpoint_dsn() -> str:
    """psycopg DSN from SQLAlchemy async URL."""
    url = (settings.database_url or "").strip()
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return url
    return url


async def get_checkpointer():
    """Return a process-wide AsyncPostgresSaver, or None if disabled/unavailable.

    HITL Approve/Rewrite still uses ``agent_pending_runs``; the checkpointer
    persists graph state per ``user_id:thread_id`` so rewrites and multi-turn
    tool loops survive process restarts.
    """
    global _pool, _saver, _setup_done
    if not settings.agent_checkpoint:
        return None
    if _saver is not None:
        return _saver
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool
    except ImportError:
        logger.warning(
            "langgraph-checkpoint-postgres / psycopg not installed; "
            "agent runs without durable checkpoint"
        )
        return None

    dsn = checkpoint_dsn()
    if not dsn:
        return None
    try:
        _pool = AsyncConnectionPool(
            conninfo=dsn,
            min_size=1,
            max_size=5,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            open=False,
        )
        await _pool.open()
        _saver = AsyncPostgresSaver(_pool)
        if not _setup_done:
            await _saver.setup()
            _setup_done = True
        logger.info("agent PostgresSaver ready")
        return _saver
    except Exception:
        logger.exception("failed to init AsyncPostgresSaver; continuing without it")
        _saver = None
        if _pool is not None:
            try:
                await _pool.close()
            except Exception:
                pass
            _pool = None
        return None


def thread_config(user_id: str, thread_id: str) -> dict:
    """LangGraph config keyed by authenticated user + client thread id."""
    safe_thread = (thread_id or "research").strip()[:128] or "research"
    return {
        "configurable": {
            "thread_id": f"{user_id}:{safe_thread}",
        }
    }
