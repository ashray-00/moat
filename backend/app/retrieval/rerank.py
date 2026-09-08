"""Hybrid retrieval rerank: local CrossEncoder, Cohere hosted, or none."""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_model = None


def load():
    global _model
    if _model is None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                "Local rerank requires sentence-transformers. "
                "Install with: pip install -e 'backend[local-rerank]' "
                "or set RERANK_PROVIDER=cohere|none."
            ) from exc
        _model = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)
    return _model


def _rerank_local(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    model = load()
    pairs = [(query, c["text"]) for c in candidates]
    scores = model.predict(pairs)
    for c, s in zip(candidates, scores):
        c["rerank_score"] = float(s)
    return sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)[:top_k]


def _rerank_none(candidates: list[dict], top_k: int) -> list[dict]:
    return candidates[:top_k]


def _rerank_cohere(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    api_key = (settings.cohere_api_key or "").strip()
    if not api_key:
        logger.warning("RERANK_PROVIDER=cohere but COHERE_API_KEY empty; using none")
        return _rerank_none(candidates, top_k)
    docs = [(c.get("text") or "")[:4000] for c in candidates]
    payload = {
        "model": settings.cohere_rerank_model or "rerank-english-v3.0",
        "query": query,
        "documents": docs,
        "top_n": min(top_k, len(docs)),
        "return_documents": False,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.post(
                "https://api.cohere.com/v2/rerank",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            res.raise_for_status()
            data = res.json()
    except Exception:
        logger.exception("Cohere rerank failed; falling back to hybrid order")
        return _rerank_none(candidates, top_k)

    results = data.get("results") or data.get("rerank_results") or []
    out: list[dict] = []
    for row in results:
        idx = row.get("index")
        if idx is None:
            continue
        try:
            i = int(idx)
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(candidates):
            item = dict(candidates[i])
            item["rerank_score"] = float(
                row.get("relevance_score") or row.get("score") or 0.0
            )
            out.append(item)
    return out[:top_k] if out else _rerank_none(candidates, top_k)


def rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    if not candidates:
        return []
    provider = (settings.rerank_provider or "local").strip().lower()
    if provider in ("none", "off", "hybrid"):
        return _rerank_none(candidates, top_k)
    if provider == "cohere":
        return _rerank_cohere(query, candidates, top_k)
    return _rerank_local(query, candidates, top_k)


async def retrieve(query: str, ticker: str | None = None, top_k: int = 5) -> list[dict]:
    from app.retrieval.search import hybrid_search

    fused = await hybrid_search(query, ticker, top_n=50)
    return rerank(query, fused, top_k=top_k)
