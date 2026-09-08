"""LLM / Agent cost and entitlement guards (DB-backed; no Redis).

Called before quota reservation so free-tier abuse and runaway spend fail closed.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text

from app.api.limits import normalize_plan
from app.config import settings
from app.db import engine


def assert_llm_enabled() -> None:
    if not settings.llm_enabled:
        raise HTTPException(
            503,
            "Research is temporarily paused. Try again later.",
        )


def agent_allowed_for_plan(plan: str | None) -> bool:
    """Whether Agent mode is available for this plan (and global flags)."""
    if not settings.llm_enabled or not settings.agent_enabled:
        return False
    if normalize_plan(plan) == "free":
        return bool(settings.free_agent_enabled)
    return True


def assert_agent_allowed(plan: str | None) -> None:
    assert_llm_enabled()
    if not settings.agent_enabled:
        raise HTTPException(503, "Agent is temporarily disabled.")
    if not agent_allowed_for_plan(plan):
        raise HTTPException(
            402,
            "Agent is not included on Free. Upgrade to Pro or use Ask.",
        )


async def _sum_cost_usd(*, user_id: str | None, since_sql: str) -> float:
    async with engine.begin() as conn:
        if user_id is None:
            row = (
                await conn.execute(
                    text(
                        "SELECT COALESCE(SUM(cost_usd), 0) AS total "
                        f"FROM usage_log WHERE created_at >= {since_sql}"
                    )
                )
            ).one()
        else:
            row = (
                await conn.execute(
                    text(
                        "SELECT COALESCE(SUM(cost_usd), 0) AS total "
                        f"FROM usage_log WHERE user_id=:u "
                        f"AND created_at >= {since_sql}"
                    ),
                    {"u": user_id},
                )
            ).one()
    return float(row.total or 0)


async def assert_daily_budgets(user_id: str) -> None:
    """Enforce optional per-user and global daily USD caps from usage_log."""
    per_user = float(settings.daily_cost_usd_per_user or 0)
    global_cap = float(settings.daily_cost_usd_global or 0)
    if per_user <= 0 and global_cap <= 0:
        return

    day = "date_trunc('day', now())"
    if per_user > 0:
        used = await _sum_cost_usd(user_id=user_id, since_sql=day)
        if used >= per_user:
            raise HTTPException(
                402,
                "Daily usage budget reached. Try again tomorrow or upgrade.",
            )
    if global_cap > 0:
        used_g = await _sum_cost_usd(user_id=None, since_sql=day)
        if used_g >= global_cap:
            raise HTTPException(
                503,
                "Service daily budget reached. Try again tomorrow.",
            )
