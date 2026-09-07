from sqlalchemy import text
from app.db import engine
from app.gateway.llm import complete

async def add_to_watchlist(user_id: str, ticker: str):
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO watchlist (user_id, ticker) VALUES (:u, :t) ON CONFLICT DO NOTHING"),
            {"u": user_id, "t": ticker.upper()})

async def get_watchlist(user_id: str) -> list[str]:
    async with engine.begin() as conn:
        rows = (await conn.execute(text(
            "SELECT ticker FROM watchlist WHERE user_id=:u"),
            {"u": user_id})).all()
    return [r.ticker for r in rows]

async def summarize_session(messages: list[dict]) -> str:
    """Compress an old transcript into a few durable sentences (mid-term memory)."""
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    res = await complete(
        [{"role": "system", "content": "Summarize this research chat in 3 sentences, "
          "keeping tickers, metrics, and the user's apparent focus."},
         {"role": "user", "content": convo}], model=None, cache_system=False, max_tokens=200)
    return res.text
