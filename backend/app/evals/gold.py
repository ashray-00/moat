"""Labeled gold queries for retrieval recall@k (section substring proof)."""

from __future__ import annotations

import json
from pathlib import Path

_GOLD_PATH = Path(__file__).with_name("gold_retrieval.json")


def load_gold_retrieval() -> list[dict]:
    raw = json.loads(_GOLD_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("gold_retrieval.json must be a non-empty list")
    out: list[dict] = []
    for i, row in enumerate(raw):
        for key in ("query", "ticker", "must_contain"):
            if not str(row.get(key) or "").strip():
                raise ValueError(f"gold case {i} missing {key}")
        out.append(
            {
                "id": row.get("id") or f"case-{i}",
                "query": str(row["query"]).strip(),
                "ticker": str(row["ticker"]).strip().upper(),
                "must_contain": str(row["must_contain"]).strip(),
            }
        )
    return out
