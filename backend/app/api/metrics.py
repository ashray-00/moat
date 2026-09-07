from fastapi import APIRouter
from sqlalchemy import text
from app.db import engine

router = APIRouter()

@router.get("/metrics/cost")
async def cost_summary():
    async with engine.begin() as conn:
        row = (await conn.execute(text(
            "SELECT count(*) reqs, sum(cost_usd) total_cost, "
            "avg(cost_usd) avg_cost, avg(latency_ms) avg_latency, "
            "sum(cached_in)::float/nullif(sum(tokens_in),0) cache_hit_rate "
            "FROM usage_log WHERE created_at > now() - interval '30 days'"))).mappings().first()
    return dict(row) if row else {}