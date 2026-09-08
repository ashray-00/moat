"""Postgres-backed pending agent runs for user-facing HITL (Approve / Rewrite)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text

from app.db import engine

PENDING_TTL = timedelta(hours=24)


async def create_pending_run(
    *,
    user_id: str,
    thread_id: str,
    query: str,
    draft_answer: str,
    messages: list[dict],
    sources: list[dict],
    series: dict | None,
) -> str:
    run_id = uuid.uuid4().hex
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO agent_pending_runs "
                "(run_id, user_id, thread_id, query, draft_answer, "
                "messages_json, sources_json, series_json, status) "
                "VALUES (:r, :u, :t, :q, :d, CAST(:m AS jsonb), "
                "CAST(:s AS jsonb), CAST(:ser AS jsonb), 'pending')"
            ),
            {
                "r": run_id,
                "u": user_id,
                "t": thread_id,
                "q": query,
                "d": draft_answer,
                "m": json.dumps(messages),
                "s": json.dumps(sources),
                "ser": json.dumps(series) if series is not None else None,
            },
        )
    return run_id


async def get_pending_run(run_id: str, user_id: str) -> dict[str, Any]:
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT run_id, user_id, thread_id, query, draft_answer, "
                    "messages_json, sources_json, series_json, status, created_at "
                    "FROM agent_pending_runs WHERE run_id=:r AND user_id=:u"
                ),
                {"r": run_id, "u": user_id},
            )
        ).mappings().first()
    if not row:
        raise HTTPException(404, "Pending run not found")
    data = dict(row)
    created = data.get("created_at")
    if created is not None:
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - created > PENDING_TTL:
            await resolve_pending(run_id, user_id, "expired")
            raise HTTPException(410, "Pending run expired. Ask again.")
    if data.get("status") != "pending":
        raise HTTPException(409, f"Run is already {data.get('status')}")

    messages = data["messages_json"]
    if isinstance(messages, str):
        messages = json.loads(messages)
    sources = data["sources_json"]
    if isinstance(sources, str):
        sources = json.loads(sources)
    series = data["series_json"]
    if isinstance(series, str):
        series = json.loads(series)

    return {
        "run_id": data["run_id"],
        "user_id": data["user_id"],
        "thread_id": data["thread_id"],
        "query": data["query"],
        "draft_answer": data["draft_answer"],
        "messages": messages if isinstance(messages, list) else [],
        "sources": sources if isinstance(sources, list) else [],
        "series": series if isinstance(series, dict) else None,
        "status": data["status"],
    }


async def resolve_pending(run_id: str, user_id: str, status: str) -> None:
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "UPDATE agent_pending_runs SET status=:s, resolved_at=now() "
                "WHERE run_id=:r AND user_id=:u AND status='pending'"
            ),
            {"s": status, "r": run_id, "u": user_id},
        )
    if (result.rowcount or 0) == 0 and status != "expired":
        # Non-pending or wrong user — get_pending_run usually catches this first.
        raise HTTPException(409, "Could not resolve pending run")
