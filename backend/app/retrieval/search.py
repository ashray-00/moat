from sqlalchemy import text
from app.db import engine
from app.gateway.embed import embed_texts

async def dense_search(query: str, ticker: str | None, k: int = 50) -> list[dict]:
    [qv] = await embed_texts([query])
    sql = ("SELECT id, ticker, section, text, is_table, "
           "1 - (embedding <=> :q) AS score FROM chunks ")
    params = {"q": str(qv), "k": k}
    if ticker:
        sql += "WHERE ticker = :tk "; params["tk"] = ticker.upper()
    sql += "ORDER BY embedding <=> :q LIMIT :k"
    async with engine.begin() as conn:
        rows = (await conn.execute(text(sql), params)).mappings().all()
    return [dict(r) for r in rows]

async def sparse_search(query: str, ticker: str | None, k: int = 50) -> list[dict]:
    sql = ("SELECT id, ticker, section, text, is_table, "
           "ts_rank(fts, plainto_tsquery('english', :q)) AS score FROM chunks "
            "WHERE fts @@ plainto_tsquery('english', :q) ")
    params = {"q": query, "k": k}
    if ticker:
        sql += "AND ticker = :tk "; params["tk"] = ticker.upper()
    sql += "ORDER BY score DESC LIMIT :k"
    async with engine.begin() as conn:
        rows = (await conn.execute(text(sql), params)).mappings().all()
    return [dict(r) for r in rows]

def rrf(result_lists: list[list[dict]], k: int = 60, top_n: int = 50) -> list[dict]:
    """Reciprocal Rank Fusion. CHunks ranked highly by BOTH lists win."""
    scores, by_id = {}, {}
    for results in result_lists:
        for rank, r in enumerate(results):
            scores[r["id"]] = scores.get(r["id"], 0.0) + 1.0 / (k + rank + 1)
            by_id[r["id"]] = r
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [{**by_id[i], "rrf": s} for i, s in ranked[:top_n]]

async def hybrid_search(query: str, ticker: str | None = None, top_n: int = 50) -> list[dict]:
    dense = await dense_search(query, ticker)
    sparse = await sparse_search(query, ticker)
    return rrf([dense, sparse], top_n=top_n)