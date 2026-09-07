from langchain_core.tools import tool
from sqlalchemy import text
from app.db import engine
from app.retrieval.rerank import retrieve as _retrieve

@tool
async def search_filings(query: str, ticker: str) -> str:
    """Search a company's SEC filings for text relevant to `query`.
    Use for qualitative questions (risks, strategy, segments).
    Example: search_filings(query="supply chain risks", ticker="AAPL").
    Returns the top excerpts with their citation ids."""
    chunks = await _retrieve(query, ticker, top_k=5)
    if not chunks:
        return f"error: no filings found for ticker={ticker}. Confirm it is covered."
    return "\n\n".join(f"[c{c['id']}] ({c['section']}) {c['text'][:600]}" for c in chunks)

@tool
async def get_financial_fact(ticker: str, metric: str, fiscal_year: int) -> str:
    """Get an exact reported financial number from XBRL.
    metric is one of: 'revenue', 'net_income'. Use for precise figures & math.
    Example: get_financial_fact(ticker="AAPL", metric="revenue", fiscal_year=2023)."""
    tag = {"revenue": "RevenueFromContractWithCustomerExcludingAssessedTax",
           "net_income": "NetIncomeLoss"}.get(metric)
    if not tag:
        return f"error: unknown metric '{metric}'. Supported: revenue, net_income."
    async with engine.begin() as conn:
        row = (await conn.execute(text(
            "SELECT val, period_end FROM facts f JOIN companies c ON f.cik=c.cik "
            "WHERE c.ticker=:t AND f.tag=:tag AND f.fy=:fy "
            "ORDER BY period_end DESC LIMIT 1"),
            {"t": ticker.upper(), "tag": tag, "fy": fiscal_year})).first()
    if not row:
        return f"error: no {metric} for {ticker} FY{fiscal_year}. Try a year we've ingested."
    return f"{ticker} {metric} FY{fiscal_year} = {row.val:.0f} USD (period end {row.period_end})"

@tool
async def compute_growth(ticker: str, metric: str, fy_start: int, fy_end: int) -> str:
    """Compute % change of a metric between two fiscal years, from filed XBRL numbers.
    Example: compute_growth(ticker="AAPL", metric="revenue", fy_start=2022, fy_end=2023)."""
    a = await get_financial_fact.ainvoke({"ticker": ticker, "metric": metric, "fiscal_year": fy_start})
    b = await get_financial_fact.ainvoke({"ticker": ticker, "metric": metric, "fiscal_year": fy_end})
    if a.startswith("error") or b.startswith("error"):
        return f"error computing growth: {a} | {b}"
    va = float(a.split("= ")[1].split(" USD")[0]); vb = float(b.split("= ")[1].split(" USD")[0])
    return f"{ticker} {metric} {fy_start}->{fy_end}: {(vb-va)/va*100:+.1f}%"