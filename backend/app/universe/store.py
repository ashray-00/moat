"""Per-user ticker additions and shared ingest_jobs on the Moat corpus."""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.db import engine
from app.ingest.universe import default_universe, is_default_ticker

logger = logging.getLogger(__name__)

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
                    "SELECT ticker, status, error "
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
    base = default_universe()
    seen = set(base)
    out = list(base)
    for t in ready:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


async def active_ingest_job(ticker: str) -> dict | None:
    t = ticker.strip().upper()
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT id, ticker, status, error FROM ingest_jobs "
                    "WHERE ticker=:t AND status = ANY(:s) "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"t": t, "s": list(IN_FLIGHT)},
            )
        ).mappings().first()
    return dict(row) if row else None


async def enqueue_ingest_job(ticker: str) -> tuple[int | None, bool]:
    """Insert a pending ingest job if none active. Returns (job_id, created_new)."""
    t = ticker.strip().upper()
    existing = await active_ingest_job(t)
    if existing:
        return int(existing["id"]), False
    async with engine.begin() as conn:
        try:
            row = (
                await conn.execute(
                    text(
                        "INSERT INTO ingest_jobs (ticker, status) "
                        "VALUES (:t, 'pending') RETURNING id"
                    ),
                    {"t": t},
                )
            ).first()
            return int(row.id), True
        except Exception:
            # Unique active-ticker race: another worker inserted first.
            logger.info("ingest job race for %s; attaching to existing", t)
    existing = await active_ingest_job(t)
    if existing:
        return int(existing["id"]), False
    return None, False


async def mark_waiting_users(ticker: str, *, status: str, error: str | None = None) -> None:
    t = ticker.strip().upper()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE user_ticker_adds SET status=:s, error=:e, updated_at=now() "
                "WHERE ticker=:t AND status = ANY(:inflight)"
            ),
            {"s": status, "e": error, "t": t, "inflight": list(IN_FLIGHT)},
        )


async def claim_next_ingest_job() -> dict | None:
    """Claim one pending job with SKIP LOCKED (multi-worker safe)."""
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "UPDATE ingest_jobs SET status='running', started_at=now(), "
                    "updated_at=now() "
                    "WHERE id = ("
                    "  SELECT id FROM ingest_jobs WHERE status='pending' "
                    "  ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1"
                    ") RETURNING id, ticker, status"
                )
            )
        ).mappings().first()
    return dict(row) if row else None


async def finish_ingest_job(
    job_id: int, *, status: str, error: str | None = None
) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ingest_jobs SET status=:s, error=:e, finished_at=now(), "
                "updated_at=now() WHERE id=:id"
            ),
            {"s": status, "e": error, "id": job_id},
        )


async def process_ingest_job(job: dict) -> None:
    """Run SEC ingest for a claimed job and wake waiting user adds."""
    ticker = job["ticker"]
    job_id = int(job["id"])
    try:
        if await company_ready(ticker):
            await finish_ingest_job(job_id, status="ready")
            await mark_waiting_users(ticker, status="ready", error=None)
            return
        from app.ingest.pipeline import ingest_company

        await ingest_company(ticker)
        if await company_ready(ticker):
            await finish_ingest_job(job_id, status="ready")
            await mark_waiting_users(ticker, status="ready", error=None)
        else:
            err = "Ingest finished but no filings were stored."
            await finish_ingest_job(job_id, status="failed", error=err)
            await mark_waiting_users(ticker, status="failed", error=err)
    except Exception as exc:
        logger.exception("ingest job failed ticker=%s", ticker)
        err = str(exc)[:300] or "ingest failed"
        await finish_ingest_job(job_id, status="failed", error=err)
        await mark_waiting_users(ticker, status="failed", error=err)


async def run_ingest_job(user_id: str, ticker: str) -> None:
    """Enqueue/claim path used by API BackgroundTasks and the worker.

    Ensures this user is pending, then processes one job for the ticker
    (or attaches to an in-flight shared job).
    """
    t = ticker.strip().upper()
    await upsert_user_add(user_id, t, status="pending", error=None)
    if await company_ready(t):
        await mark_waiting_users(t, status="ready", error=None)
        return

    job_id, created = await enqueue_ingest_job(t)
    if not created:
        # Another job is running; user stays pending until mark_waiting_users.
        return

    # Process immediately when we created the job (single-box / kick).
    job = {"id": job_id, "ticker": t, "status": "pending"}
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ingest_jobs SET status='running', started_at=now(), "
                "updated_at=now() WHERE id=:id AND status='pending'"
            ),
            {"id": job_id},
        )
    await process_ingest_job({**job, "status": "running"})


async def list_recent_ingest_jobs(limit: int = 50) -> list[dict]:
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, ticker, status, error, created_at, started_at, finished_at "
                    "FROM ingest_jobs ORDER BY id DESC LIMIT :n"
                ),
                {"n": limit},
            )
        ).mappings().all()
    return [dict(r) for r in rows]


async def list_companies(limit: int = 200) -> list[dict]:
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT ticker, name, cik FROM companies ORDER BY ticker LIMIT :n"
                ),
                {"n": limit},
            )
        ).mappings().all()
    return [dict(r) for r in rows]
