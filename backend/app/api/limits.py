from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import text

from app.db import engine

PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "label": "Free",
        "monthly_asks": 5,
        "rpm": 10,
        "universe_add_limit": 0,
        "ingest_per_hour": 0,
        "checkout": False,
    },
    "pro": {
        "label": "Pro",
        "monthly_asks": 500,
        "rpm": 60,
        "universe_add_limit": 10,
        "ingest_per_hour": 2,
        "checkout": True,
    },
    "team": {
        "label": "Team",
        "monthly_asks": 5000,
        "rpm": 120,
        "universe_add_limit": 50,
        "ingest_per_hour": 6,
        "checkout": True,
    },
}

# Back-compat for any import of PLAN_LIMITS
PLAN_LIMITS = {k: int(v["monthly_asks"]) for k, v in PLANS.items()}


def normalize_plan(plan: str | None) -> str:
    if plan and plan in PLANS:
        return plan
    return "free"


def plan_config(plan: str | None) -> dict[str, Any]:
    return PLANS[normalize_plan(plan)]


def plan_rpm(plan: str | None) -> int:
    return int(plan_config(plan)["rpm"])


def monthly_ask_limit(plan: str | None) -> int:
    return int(plan_config(plan)["monthly_asks"])


def universe_add_limit(plan: str | None) -> int:
    return int(plan_config(plan)["universe_add_limit"])


def ingest_per_hour(plan: str | None) -> int:
    return int(plan_config(plan)["ingest_per_hour"])


def list_public_plans() -> list[dict[str, Any]]:
    return [
        {
            "id": plan_id,
            "label": cfg["label"],
            "monthly_asks": cfg["monthly_asks"],
            "rpm": cfg["rpm"],
            "universe_add_limit": cfg["universe_add_limit"],
            "ingest_per_hour": cfg["ingest_per_hour"],
            "checkout": cfg["checkout"],
        }
        for plan_id, cfg in PLANS.items()
    ]


async def _month_usage(user_id: str) -> tuple[int, str]:
    """Return (used_count, period_start_iso) using the same DB month window as quotas."""
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT count(*) AS used, "
                    "date_trunc('month', now()) AS period_start "
                    "FROM usage_log WHERE user_id=:u "
                    "AND created_at >= date_trunc('month', now())"
                ),
                {"u": user_id},
            )
        ).one()
    period = row.period_start
    if hasattr(period, "isoformat"):
        period_iso = period.isoformat()
    else:
        period_iso = str(period)
    return int(row.used), period_iso


async def enforce_quota(user_id: str, plan: str) -> None:
    key = normalize_plan(plan)
    limit = monthly_ask_limit(key)
    used, _ = await _month_usage(user_id)
    if used >= limit:
        raise HTTPException(
            402,
            f"Monthly {key} limit reached ({limit}). Upgrade to continue.",
        )


async def usage_snapshot(user_id: str, plan: str | None) -> dict[str, Any]:
    from app.universe.store import count_user_adds

    key = normalize_plan(plan)
    cfg = plan_config(key)
    limit = int(cfg["monthly_asks"])
    used, period_start = await _month_usage(user_id)
    remaining = max(0, limit - used)
    add_limit = int(cfg["universe_add_limit"])
    adds_used = await count_user_adds(user_id)
    return {
        "plan": key,
        "label": cfg["label"],
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "rpm": int(cfg["rpm"]),
        "period_start": period_start,
        "universe_adds_used": adds_used,
        "universe_add_limit": add_limit,
        "ingest_per_hour": int(cfg["ingest_per_hour"]),
    }


async def log_usage(
    user_id: str,
    *,
    model: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    cached_in: int = 0,
    cost_usd: float = 0.0,
    latency_ms: int = 0,
) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO usage_log "
                "(user_id, model, tokens_in, tokens_out, cached_in, cost_usd, latency_ms) "
                "VALUES (:u, :m, :ti, :to, :ci, :c, :l)"
            ),
            {
                "u": user_id,
                "m": model,
                "ti": tokens_in,
                "to": tokens_out,
                "ci": cached_in,
                "c": cost_usd,
                "l": latency_ms,
            },
        )
