from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import text

from app.config import settings
from app.db import engine

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/cost")
async def cost_summary(x_metrics_token: str | None = Header(default=None)):
    if not settings.metrics_token:
        raise HTTPException(503, "METRICS_TOKEN is not configured")
    if x_metrics_token != settings.metrics_token:
        raise HTTPException(401, "invalid metrics token")

    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT count(*) reqs, sum(cost_usd) total_cost, "
                    "avg(cost_usd) avg_cost, avg(latency_ms) avg_latency, "
                    "sum(cached_in)::float/nullif(sum(tokens_in),0) cache_hit_rate "
                    "FROM usage_log WHERE created_at > now() - interval '30 days'"
                )
            )
        ).mappings().first()
    return dict(row) if row else {}
