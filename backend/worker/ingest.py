"""DB-backed ingest worker: claim pending ingest_jobs with SKIP LOCKED."""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.universe import store as ustore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker.ingest")


async def run_once() -> bool:
    job = await ustore.claim_next_ingest_job()
    if not job:
        return False
    logger.info("processing %s (job %s)", job["ticker"], job["id"])
    await ustore.process_ingest_job(job)
    return True


async def run_loop(poll_seconds: float = 2.0) -> None:
    logger.info("ingest worker started (poll=%.1fs)", poll_seconds)
    while True:
        try:
            did = await run_once()
            if not did:
                await asyncio.sleep(poll_seconds)
        except Exception:
            logger.exception("worker loop error")
            await asyncio.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Moat SEC ingest worker")
    parser.add_argument("--once", action="store_true", help="Process at most one job")
    parser.add_argument("--poll", type=float, default=2.0)
    args = parser.parse_args()
    if args.once:
        asyncio.run(run_once())
    else:
        asyncio.run(run_loop(args.poll))


if __name__ == "__main__":
    main()
