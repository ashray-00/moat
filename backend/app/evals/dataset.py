from sqlalchemy import text
from app.db import engine

async def generate_factual_cases() -> list[dict]:
    """Auto-build factual eval cases from the XBRL facts table (ground truth)."""
    async with engine.begin() as conn:
        rows = (await conn.execute(text(
            "SELECT c.ticker, f.fy, f.tag, f.val FROM facts f "
            "JOIN companies c ON f.cik=c.cik WHERE f.tag LIKE '%Revenue%'"))).all()
    cases = []
    for r in rows:
        cases.append({
            "query": f"What was {r.ticker}'s revenue in FY{r.fy}?",
            "ticker": r.ticker,
            "expected_number": float(r.val),   # ground truth
            "kind": "factual",
        })
    return cases

# Hand-written qualitative cases (retrieval correctness, not exact numbers)
QUALITATIVE_CASES = [
    {"query": "What supply-chain risks does Apple disclose?", "ticker": "AAPL",
     "must_retrieve_section": "Risk Factors", "kind": "qualitative"},
    {"query": "How does NVIDIA describe its data-center segment?", "ticker": "NVDA",
     "must_retrieve_section": "Business", "kind": "qualitative"},
]