import json

import pytest

from app.agent import tools as tools_mod


def test_normalize_metric_aliases():
    assert tools_mod._normalize_metric("Revenue") == "revenue"
    assert tools_mod._normalize_metric("sales") == "revenue"
    assert tools_mod._normalize_metric("earnings") == "net_income"
    assert tools_mod._normalize_metric("nope") is None


@pytest.mark.asyncio
async def test_compute_growth_numeric(monkeypatch):
    async def fake_fact(ticker, metric_key, fy):
        vals = {2022: 100.0, 2023: 150.0}
        if fy not in vals:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "value": vals[fy], "metric": metric_key, "ticker": ticker}

    monkeypatch.setattr(tools_mod, "_fact_value", fake_fact)
    tools = tools_mod.make_agent_tools("u1")
    growth = next(t for t in tools if t.name == "compute_growth")
    raw = await growth.ainvoke(
        {"ticker": "AAPL", "metric": "revenue", "fy_start": 2022, "fy_end": 2023}
    )
    data = json.loads(raw)
    assert data["ok"] is True
    assert data["growth_pct"] == 50.0


@pytest.mark.asyncio
async def test_unknown_metric_error():
    tools = tools_mod.make_agent_tools("u1")
    fact = next(t for t in tools if t.name == "get_financial_fact")
    raw = await fact.ainvoke(
        {"ticker": "AAPL", "metric": "ebitda", "fiscal_year": 2023}
    )
    data = json.loads(raw)
    assert data["ok"] is False
    assert data["error"] == "unknown_metric"
