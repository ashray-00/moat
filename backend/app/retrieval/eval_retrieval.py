async def recall_at_k(cases: list[dict], k: int = 5) -> float:
    """cases: [{'query':..., 'ticker':..., 'must_contain': 'substring proving the right chunk'}]

    A hit counts when ``must_contain`` appears in chunk text **or** section.
    recall@k = fraction of queries with a gold hit in the top-k.
    """
    from app.retrieval.rerank import retrieve

    hits = 0
    for c in cases:
        needle = c["must_contain"].lower()
        got = await retrieve(c["query"], c["ticker"], top_k=k)
        if any(
            needle in (r.get("text") or "").lower()
            or needle in (r.get("section") or "").lower()
            for r in got
        ):
            hits += 1
    return hits / len(cases) if cases else 0.0
