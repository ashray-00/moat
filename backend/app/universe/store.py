"""Per-user ticker additions on top of the shared DEFAULT_UNIVERSE corpus."""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.db import engine
from app.ingest.universe import DEFAULT_UNIVERSE, is_default_ticker

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("pending", "running", "ready", "failed")
IN_FLIGHT = ("pending", "running")


async def company_ready(ticker: str) -> bool:
    """True when shared DB already has usable filing chunks for this ticker."""
    t = ticker.strip().upper()
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT 1 FROM companies c "
                    "WHERE c.ticker=:t AND EXISTS ("
                    "  SELECT 1 FROM chunks ch WHERE ch.ticker=c.ticker LIMIT 1"
                    ") LIMIT 1"
                ),
                {"t": t},
            )
        ).first()
    return row is not None


async def count_user_adds(user_id: str) -> int:
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT count(*) AS n FROM user_ticker_adds WHERE user_id=:u"),
                {"u": user_id},
            )
        ).one()
    return int(row.n)


async def list_user_adds(user_id: str) -> list[dict]:
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT ticker, status, error, created_at, updated_at "
                    "FROM user_ticker_adds WHERE user_id=:u ORDER BY ticker"
                ),
                {"u": user_id},
            )
        ).mappings().all()
    out = []
    for r in rows:
        item = {"ticker": r["ticker"], "status": r["status"]}
        if r.get("error"):
            item["error"] = r["error"]
        out.append(item)
    return out


async def get_user_add(user_id: str, ticker: str) -> dict | None:
    t = ticker.strip().upper()
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT ticker, status, error FROM user_ticker_adds "
                    "WHERE user_id=:u AND ticker=:t"
                ),
                {"u": user_id, "t": t},
            )
        ).mappings().first()
    return dict(row) if row else None


async def has_in_flight_ingest(user_id: str) -> bool:
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT 1 FROM user_ticker_adds "
                    "WHERE user_id=:u AND status = ANY(:s) LIMIT 1"
                ),
                {"u": user_id, "s": list(IN_FLIGHT)},
            )
        ).first()
    return row is not None


async def upsert_user_add(
    user_id: str, ticker: str, *, status: str, error: str | None = None
) -> dict:
    t = ticker.strip().upper()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO user_ticker_adds (user_id, ticker, status, error) "
                "VALUES (:u, :t, :s, :e) "
                "ON CONFLICT (user_id, ticker) DO UPDATE SET "
                "status=:s, error=:e, updated_at=now()"
            ),
            {"u": user_id, "t": t, "s": status, "e": error},
        )
    return {"ticker": t, "status": status, **({"error": error} if error else {})}


async def set_add_status(
    user_id: str, ticker: str, *, status: str, error: str | None = None
) -> None:
    t = ticker.strip().upper()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE user_ticker_adds SET status=:s, error=:e, updated_at=now() "
                "WHERE user_id=:u AND ticker=:t"
            ),
            {"u": user_id, "t": t, "s": status, "e": error},
        )


async def delete_user_add(user_id: str, ticker: str) -> bool:
    """Remove a user addition only. Never touches shared companies/chunks."""
    t = ticker.strip().upper()
    if is_default_ticker(t):
        return False
    async with engine.begin() as conn:
        res = await conn.execute(
            text("DELETE FROM user_ticker_adds WHERE user_id=:u AND ticker=:t"),
            {"u": user_id, "t": t},
        )
    return bool(res.rowcount)


async def effective_universe(user_id: str) -> list[str]:
    """Defaults plus this user's ready additions (for agent search)."""
    adds = await list_user_adds(user_id)
    ready = [a["ticker"] for a in adds if a["status"] == "ready"]
    seen = set(DEFAULT_UNIVERSE)
    out = list(DEFAULT_UNIVERSE)
    for t in ready:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


async def run_ingest_job(user_id: str, ticker: str) -> None:
    """Background: ingest into shared DB, then mark this user's add ready/failed."""
    t = ticker.strip().upper()
    try:
        await set_add_status(user_id, t, status="running")
        # Re-check shared DB in case another user's job finished first.
        if await company_ready(t):
            await set_add_status(user_id, t, status="ready", error=None)
            return
        from app.ingest.pipeline import ingest_company

        await ingest_company(t)
        if await company_ready(t):
            await set_add_status(user_id, t, status="ready", error=None)
        else:
            await set_add_status(
                user_id,
                t,
                status="failed",
                error="Ingest finished but no filings were stored.",
            )
    except Exception as exc:
        logger.exception("ingest failed user=%s ticker=%s", user_id, t)
        await set_add_status(
            user_id, t, status="failed", error=str(exc)[:300] or "ingest failed"
        )
