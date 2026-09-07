from sentence_transformers import CrossEncoder

_model = None
def load():
    global _model
    if _model is None:
        _model = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)
    return _model

def rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    if not candidates:
        return []
    model = load()
    pairs = [(query, c["text"]) for c in candidates]
    scores = model.predict(pairs)
    for c, s in zip(candidates, scores):
        c["rerank_score"] = float(s)
    return sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)[:top_k]

async def retrieve(query: str, ticker: str | None = None, top_k: int = 5) -> list[dict]:
    from app.retrieval.search import hybrid_search
    fused = await hybrid_search(query, ticker, top_n = 50)
    return rerank(query, fused, top_k=top_k)