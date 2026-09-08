"""Research agent tools — structured JSON strings for the desk UI and LLM."""

from __future__ import annotations

import json

from langchain_core.tools import StructuredTool
from sqlalchemy import text

from app.db import engine
from app.ingest.facts import NET_INCOME_TAGS, REVENUE_TAGS
from app.retrieval.rerank import retrieve as _retrieve
from app.safety.guards import sanitize_retrieved
from app.universe.store import effective_universe

METRIC_TAGS: dict[str, list[str]] = {
    "revenue": REVENUE_TAGS,
    "net_income": NET_INCOME_TAGS,
}

AGENT_SYSTEM = """You are Moat, an equity-research desk agent over SEC filings and XBRL facts.

Rules:
1. Prefer tools over invention. For qualitative questions use search_filings; for numbers use get_financial_fact / get_metric_series / compute_growth.
2. Cite filing excerpts as [cite:cN] using citation_id values returned by search tools. Never invent citation ids.
3. You are research-only — never tell the user to buy, sell, or hold; never predict prices.
4. If tools return ok=false, say what is missing (ticker not ingested, year missing, empty coverage).
5. Be concise and neutral. When you have a multi-year series, summarize the trend and cite the figures.
6. search_watchlist searches the user's coverage universe (defaults plus ready custom tickers).
"""


def _ok(payload: dict) -> str:
    return json.dumps({"ok": True, **payload})


def _err(code: str, message: str, **extra) -> str:
    return json.dumps({"ok": False, "error": code, "message": message, **extra})


def _normalize_metric(metric: str) -> str | None:
    key = metric.strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "rev": "revenue",
        "sales": "revenue",
        "income": "net_income",
        "netincome": "net_income",
        "earnings": "net_income",
    }
    key = aliases.get(key, key)
    return key if key in METRIC_TAGS else None


async def _fact_value(ticker: str, metric_key: str, fiscal_year: int) -> dict:
    tags = METRIC_TAGS[metric_key]
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT f.tag, f.val, f.period_end, f.form FROM facts f "
                    "JOIN companies c ON f.cik=c.cik "
                    "WHERE c.ticker=:t AND f.fy=:fy AND f.tag = ANY(:tags) "
                    "ORDER BY array_position(:tags, f.tag), f.period_end DESC "
                    "LIMIT 1"
                ),
                {"t": ticker.upper(), "fy": fiscal_year, "tags": tags},
            )
        ).mappings().first()
    if not row:
        return {
            "ok": False,
            "error": "not_found",
            "message": (
                f"No {metric_key} for {ticker} FY{fiscal_year}. "
                f"Supported metrics: {', '.join(METRIC_TAGS)}. "
                "Confirm the ticker is ingested."
            ),
        }
    return {
        "ok": True,
        "ticker": ticker.upper(),
        "metric": metric_key,
        "fiscal_year": fiscal_year,
        "value": float(row["val"]),
        "unit": "USD",
        "period_end": str(row["period_end"]),
        "tag": row["tag"],
        "form": row["form"],
    }


def make_agent_tools(user_id: str) -> list:
    """Build tool list with watchlist bound to the authenticated user."""

    async def list_available_metrics() -> str:
        """List financial metrics Moat can look up from filed XBRL facts."""
        return _ok(
            {
                "metrics": [
                    {"id": "revenue", "label": "Revenue"},
                    {"id": "net_income", "label": "Net income"},
                ]
            }
        )

    async def search_filings(query: str, ticker: str, top_k: int = 5) -> str:
        """Search a company's SEC filings for text relevant to query.
        Returns structured excerpts with citation ids (cN)."""
        t = ticker.strip().upper()
        allowed = {x.upper() for x in await effective_universe(user_id)}
        if t not in allowed:
            return _err(
                "ticker_not_in_coverage",
                f"{t} is not in your coverage universe.",
                ticker=t,
            )
        k = max(1, min(int(top_k or 5), 8))
        chunks = await _retrieve(query, t, top_k=k)
        if not chunks:
            return _err(
                "no_filings",
                f"No filings found for ticker={ticker.upper()}. Confirm it is covered.",
                ticker=ticker.upper(),
            )
        excerpts = [
            {
                "citation_id": f"c{c['id']}",
                "chunk_id": c["id"],
                "ticker": c.get("ticker") or ticker.upper(),
                "section": c.get("section") or "",
                "excerpt": sanitize_retrieved((c.get("text") or "")[:800]),
                "score": c.get("score"),
            }
            for c in chunks
        ]
        return _ok({"ticker": ticker.upper(), "query": query, "excerpts": excerpts})

    async def _require_ticker(ticker: str) -> str | None:
        t = ticker.strip().upper()
        allowed = {x.upper() for x in await effective_universe(user_id)}
        if t not in allowed:
            return _err(
                "ticker_not_in_coverage",
                f"{t} is not in your coverage universe.",
                ticker=t,
            )
        return None

    async def get_financial_fact(ticker: str, metric: str, fiscal_year: int) -> str:
        """Get an exact reported financial number from XBRL for a fiscal year.
        metric: revenue or net_income (aliases: sales, earnings)."""
        denied = await _require_ticker(ticker)
        if denied:
            return denied
        key = _normalize_metric(metric)
        if not key:
            return _err(
                "unknown_metric",
                f"Unknown metric '{metric}'. Supported: {', '.join(METRIC_TAGS)}.",
                supported=list(METRIC_TAGS),
            )
        result = await _fact_value(ticker, key, int(fiscal_year))
        return json.dumps(result) if not result.get("ok") else _ok(result)

    async def get_metric_series(ticker: str, metric: str, limit: int = 5) -> str:
        """Return recent fiscal-year values for a metric (oldest→newest)."""
        denied = await _require_ticker(ticker)
        if denied:
            return denied
        key = _normalize_metric(metric)
        if not key:
            return _err(
                "unknown_metric",
                f"Unknown metric '{metric}'. Supported: {', '.join(METRIC_TAGS)}.",
                supported=list(METRIC_TAGS),
            )
        lim = max(1, min(int(limit or 5), 12))
        tags = METRIC_TAGS[key]
        async with engine.begin() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT DISTINCT ON (f.fy) f.fy, f.val, f.period_end, f.tag "
                        "FROM facts f JOIN companies c ON f.cik=c.cik "
                        "WHERE c.ticker=:t AND f.tag = ANY(:tags) "
                        "ORDER BY f.fy DESC, array_position(:tags, f.tag), "
                        "f.period_end DESC"
                    ),
                    {"t": ticker.upper(), "tags": tags},
                )
            ).mappings().all()
        rows = list(reversed(rows[:lim]))
        if not rows:
            return _err(
                "not_found",
                f"No {key} series for {ticker.upper()}.",
                ticker=ticker.upper(),
                metric=key,
            )
        series = [
            {
                "fiscal_year": int(r["fy"]),
                "value": float(r["val"]),
                "period_end": str(r["period_end"]),
                "tag": r["tag"],
            }
            for r in rows
        ]
        return _ok(
            {
                "ticker": ticker.upper(),
                "metric": key,
                "unit": "USD",
                "series": series,
            }
        )

    async def compute_growth(
        ticker: str, metric: str, fy_start: int, fy_end: int
    ) -> str:
        """Compute % change of a metric between two fiscal years from XBRL."""
        denied = await _require_ticker(ticker)
        if denied:
            return denied
        key = _normalize_metric(metric)
        if not key:
            return _err(
                "unknown_metric",
                f"Unknown metric '{metric}'. Supported: {', '.join(METRIC_TAGS)}.",
            )
        a = await _fact_value(ticker, key, int(fy_start))
        b = await _fact_value(ticker, key, int(fy_end))
        if not a.get("ok") or not b.get("ok"):
            return _err(
                "growth_inputs",
                "Could not load both years for growth.",
                start=a,
                end=b,
            )
        va, vb = float(a["value"]), float(b["value"])
        if va == 0:
            return _err(
                "div_zero", f"Start-year {key} is zero; cannot compute growth."
            )
        pct = (vb - va) / va * 100.0
        return _ok(
            {
                "ticker": ticker.upper(),
                "metric": key,
                "fy_start": int(fy_start),
                "fy_end": int(fy_end),
                "value_start": va,
                "value_end": vb,
                "growth_pct": round(pct, 2),
                "unit": "USD",
            }
        )

    async def search_watchlist(query: str, top_k_per_ticker: int = 2) -> str:
        """Search filings across this user's coverage universe (defaults + ready adds)."""
        tickers = await effective_universe(user_id)
        if not tickers:
            return _err(
                "empty_universe",
                "No tickers in coverage. Defaults should always be present.",
            )
        k = max(1, min(int(top_k_per_ticker or 2), 4))
        by_ticker = []
        for t in tickers:
            chunks = await _retrieve(query, t, top_k=k)
            excerpts = [
                {
                    "citation_id": f"c{c['id']}",
                    "chunk_id": c["id"],
                    "ticker": t,
                    "section": c.get("section") or "",
                    "excerpt": sanitize_retrieved((c.get("text") or "")[:500]),
                }
                for c in chunks
            ]
            by_ticker.append({"ticker": t, "excerpts": excerpts})
        return _ok({"query": query, "tickers": tickers, "results": by_ticker})

    return [
        StructuredTool.from_function(
            coroutine=list_available_metrics, name="list_available_metrics"
        ),
        StructuredTool.from_function(
            coroutine=search_filings, name="search_filings"
        ),
        StructuredTool.from_function(
            coroutine=get_financial_fact, name="get_financial_fact"
        ),
        StructuredTool.from_function(
            coroutine=get_metric_series, name="get_metric_series"
        ),
        StructuredTool.from_function(
            coroutine=compute_growth, name="compute_growth"
        ),
        StructuredTool.from_function(
            coroutine=search_watchlist, name="search_watchlist"
        ),
    ]
