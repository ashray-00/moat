from sqlalchemy import text

from app.db import engine
from app.gateway.embed import embed_texts


async def get_cached(query: str, threshold: float = 0.97) -> str | None:
    """Return a prior answer if a very-similar question was answered before."""
    [qv] = await embed_texts([query])
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT answer, 1 - (embedding <=> :q) AS sim FROM answer_cache "
                    "ORDER BY embedding <=> :q LIMIT 1"
                ),
                {"q": str(qv)},
            )
        ).first()
    return row.answer if row and row.sim >= threshold else None


async def put_cache(query: str, answer: str) -> None:
    [qv] = await embed_texts([query])
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO answer_cache (query, answer, embedding) "
                "VALUES (:q, :a, :e)"
            ),
            {"q": query, "a": answer, "e": str(qv)},
        )
