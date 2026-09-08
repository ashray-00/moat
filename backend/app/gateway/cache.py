from sqlalchemy import text

from app.db import engine
from app.gateway.embed import embed_texts


async def get_cached(
    query: str, *, user_id: str, threshold: float = 0.97
) -> str | None:
    """Return a prior answer for this user if a very-similar question was asked."""
    [qv] = await embed_texts([query])
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT answer, 1 - (embedding <=> :q) AS sim FROM answer_cache "
                    "WHERE user_id=:u "
                    "ORDER BY embedding <=> :q LIMIT 1"
                ),
                {"q": str(qv), "u": user_id},
            )
        ).first()
    return row.answer if row and row.sim >= threshold else None


async def put_cache(query: str, answer: str, *, user_id: str) -> None:
    [qv] = await embed_texts([query])
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO answer_cache (user_id, query, answer, embedding) "
                "VALUES (:u, :q, :a, :e)"
            ),
            {"u": user_id, "q": query, "a": answer, "e": str(qv)},
        )
