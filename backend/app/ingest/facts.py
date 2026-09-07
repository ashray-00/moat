REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
]

NET_INCOME_TAGS = ["NetIncomeLoss"]

def annual_series(facts: dict, tags: list[str]) -> tuple[str | None, list[dict]]:
    """Fist matching tag's dedup's annual (FY, 10-K) values, oldest -> newest."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        if tag not in gaap:
            continue
        rows = gaap[tag]["units"].get("USD", [])
        annual = [r for r in rows if r.get("fp") == "FY" and r.get("form", "").startswith("10-K")]
        seen = {}
        for r in annual:
            key = (r["fy"], r["end"])
            seen.setdefault(key, r)
        return tag, sorted(seen.values(), key=lambda r: r["end"])
    return None, []

def yoy_growth(series: list[dict]) -> float | None:
    if len(series) < 2:
        return None
    prev, curr = series[-2]["val"], series[-1]["val"]
    return (curr - prev) / prev * 100 if prev else None