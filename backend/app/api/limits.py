from sqlalchemy import text
from fastapi import HTTPException
from app.db import engine

PLAN_LIMITS = {"free": 5, "pro": 500, "team": 5000}

async def enforce_quota(user_id: str, plan: str):
    limit = PLAN_LIMITS.get(plan, 5)
    async with engine.begin() as conn:
        used = (await conn.execute(text(
            "SELECT count(*) FROM usage_log WHERE user_id=:u "
            "AND created_at > date_trunc('month', now())"), {"u": user_id})).scalar_one()
    if used >= limit:
        raise HTTPException(402, f"Monthly {plan} limit reached ({limit}). Upgrade to continue.")