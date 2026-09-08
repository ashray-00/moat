from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import RequiredUser, get_user_plan
from app.api.limits import (
    ingest_per_hour,
    normalize_plan,
    plan_config,
    universe_add_limit,
)
from app.api.ratelimit import check_rate_limit
from app.ingest.universe import default_universe, is_default_ticker
from app.universe import store as ustore

router = APIRouter(prefix="/universe", tags=["universe"])


class AddTickerBody(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)


def _normalize_ticker(raw: str) -> str:
    t = raw.strip().upper()
    if not t.isalnum() or len(t) > 10:
        raise HTTPException(400, "invalid ticker")
    return t


@router.get("")
async def get_universe(user_id: RequiredUser):
    plan = normalize_plan(await get_user_plan(user_id))
    cfg = plan_config(plan)
    added = await ustore.list_user_adds(user_id)
    used = len(added)
    limit = int(cfg["universe_add_limit"])
    return {
        "default": default_universe(),
        "added": added,
        "limit": limit,
        "used": used,
        "can_modify": limit > 0,
        "plan": plan,
        "ingest_per_hour": int(cfg["ingest_per_hour"]),
    }


@router.post("/tickers")
async def add_ticker(
    body: AddTickerBody,
    user_id: RequiredUser,
    background_tasks: BackgroundTasks,
):
    plan = normalize_plan(await get_user_plan(user_id))
    limit = universe_add_limit(plan)
    if limit <= 0:
        raise HTTPException(
            403,
            "Custom tickers require Pro or Team. Upgrade to add coverage.",
        )

    ticker = _normalize_ticker(body.ticker)
    if is_default_ticker(ticker):
        raise HTTPException(
            400,
            f"{ticker} is already in the default coverage list.",
        )

    existing = await ustore.get_user_add(user_id, ticker)
    if existing:
        # Idempotent: return current row (retry failed by re-queue below).
        if existing["status"] in ("ready", "pending", "running"):
            return {
                "ticker": existing["ticker"],
                "status": existing["status"],
                "error": existing.get("error"),
                "started_ingest": False,
            }
        # failed → allow retry below

    used = await ustore.count_user_adds(user_id)
    if not existing and used >= limit:
        raise HTTPException(
            403,
            f"Universe add limit reached ({limit}). Upgrade or remove a ticker.",
        )

    # Shared DB fast-path — no ingest quota burn.
    if await ustore.company_ready(ticker):
        row = await ustore.upsert_user_add(user_id, ticker, status="ready")
        return {**row, "started_ingest": False}

    if await ustore.has_in_flight_ingest(user_id):
        raise HTTPException(
            429,
            "An ingest is already running. Wait for it to finish.",
        )

    check_rate_limit(
        f"ingest:{user_id}",
        limit=ingest_per_hour(plan),
        window_seconds=3600.0,
    )

    row = await ustore.upsert_user_add(user_id, ticker, status="pending", error=None)
    background_tasks.add_task(ustore.run_ingest_job, user_id, ticker)
    return {**row, "started_ingest": True}


@router.delete("/tickers/{ticker}")
async def remove_ticker(ticker: str, user_id: RequiredUser):
    plan = normalize_plan(await get_user_plan(user_id))
    if universe_add_limit(plan) <= 0:
        raise HTTPException(
            403,
            "Custom tickers require Pro or Team.",
        )
    t = _normalize_ticker(ticker)
    if is_default_ticker(t):
        raise HTTPException(400, "Cannot remove a default coverage ticker.")
    ok = await ustore.delete_user_add(user_id, t)
    if not ok:
        raise HTTPException(404, "Ticker is not on your custom list.")
    return await get_universe(user_id)
