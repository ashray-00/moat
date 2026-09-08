"""Tiered research memory.

- Working: short `recent` buffer (current conversation turns)
- Mid-term: compacted `summary` in Postgres
- When `recent` grows past the cap, oldest turns are folded into `summary`
  (no full transcript table — compaction only sees summary + working buffer)
"""

from __future__ import annotations

import json

from sqlalchemy import text

from app.db import engine
from app.gateway.llm import complete

# Keep this many messages in working memory (user+assistant pairs ≈ half).
WORKING_MAX = 8
# After compaction, leave this many newest messages in working memory.
WORKING_KEEP = 4


async def add_to_watchlist(user_id: str, ticker: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO watchlist (user_id, ticker) VALUES (:u, :t) "
                "ON CONFLICT DO NOTHING"
            ),
            {"u": user_id, "t": ticker.upper()},
        )


async def remove_from_watchlist(user_id: str, ticker: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM watchlist WHERE user_id=:u AND ticker=:t"),
            {"u": user_id, "t": ticker.upper()},
        )


async def get_watchlist(user_id: str) -> list[str]:
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text("SELECT ticker FROM watchlist WHERE user_id=:u ORDER BY ticker"),
                {"u": user_id},
            )
        ).all()
    return [r.ticker for r in rows]


def _parse_recent(raw) -> list[dict]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        return []
    out = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        role, content = m.get("role"), m.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content:
            out.append({"role": role, "content": content})
    return out


async def load_memory(user_id: str, thread_id: str) -> dict:
    """Return {summary, recent} for a research thread."""
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT summary, recent FROM session_summaries "
                    "WHERE user_id=:u AND thread_id=:t"
                ),
                {"u": user_id, "t": thread_id},
            )
        ).mappings().first()
    if not row:
        return {"summary": None, "recent": []}
    return {
        "summary": row["summary"],
        "recent": _parse_recent(row["recent"]),
    }


async def _save_memory(
    user_id: str,
    thread_id: str,
    *,
    summary: str | None,
    recent: list[dict],
) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO session_summaries (user_id, thread_id, summary, recent, updated_at) "
                "VALUES (:u, :t, :s, CAST(:r AS jsonb), now()) "
                "ON CONFLICT (user_id, thread_id) DO UPDATE SET "
                "summary=EXCLUDED.summary, recent=EXCLUDED.recent, updated_at=now()"
            ),
            {
                "u": user_id,
                "t": thread_id,
                "s": summary,
                "r": json.dumps(recent),
            },
        )


async def get_session_summary(user_id: str, thread_id: str) -> str | None:
    mem = await load_memory(user_id, thread_id)
    return mem["summary"]


async def upsert_session_summary(user_id: str, thread_id: str, summary: str) -> None:
    mem = await load_memory(user_id, thread_id)
    await _save_memory(user_id, thread_id, summary=summary, recent=mem["recent"])


async def summarize_session(messages: list[dict]) -> str:
    """Compress turns into a few durable sentences (mid-term memory)."""
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    res = await complete(
        [
            {
                "role": "system",
                "content": (
                    "Summarize this research chat in 3 sentences, "
                    "keeping tickers, metrics, and the user's apparent focus."
                ),
            },
            {"role": "user", "content": convo},
        ],
        model=None,
        cache_system=False,
        max_tokens=200,
    )
    return res.text


async def _compact(
    summary: str | None,
    old_turns: list[dict],
) -> str:
    """Fold older working-memory turns into the mid-term summary."""
    parts: list[dict] = []
    if summary:
        parts.append(
            {
                "role": "user",
                "content": f"Existing session summary:\n{summary}",
            }
        )
    parts.extend(old_turns)
    return await summarize_session(parts)


async def remember_turn(
    user_id: str,
    thread_id: str,
    query: str,
    answer: str,
) -> dict:
    """Append the latest Q/A to working memory; compact into summary if too long."""
    mem = await load_memory(user_id, thread_id)
    summary = mem["summary"]
    recent = list(mem["recent"])
    recent.append({"role": "user", "content": query})
    recent.append({"role": "assistant", "content": answer[:4000]})

    if len(recent) > WORKING_MAX:
        overflow = recent[:-WORKING_KEEP]
        keep = recent[-WORKING_KEEP:]
        try:
            summary = await _compact(summary, overflow)
        except Exception:
            # If compaction LLM fails, still keep a trimmed working buffer.
            keep = recent[-WORKING_KEEP:]
        recent = keep

    await _save_memory(user_id, thread_id, summary=summary, recent=recent)
    return {"summary": summary, "recent": recent}
