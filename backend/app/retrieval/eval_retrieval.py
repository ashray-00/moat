async def recall_at_k(cases: list[dict], k: int = 5) -> float:
    """cases: [{'query':..., 'ticker':..., 'must_contain': 'substring that proves the right chunk'}]
    recall@k = fraction of queries where a gold chunk is in the top-k."""
    from app.retrieval.rerank import retrieve
    hits = 0
    for c in cases:
        got = await retrieve(c["query"], c["ticker"], top_k=k)
        if any(c["must_contain"].lower() in r["text"].lower() for r in got):
            hits += 1
    return hits / len(cases) if cases else 0.0