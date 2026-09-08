import pytest
from fastapi import HTTPException

from app.api import limits
from app.api.ratelimit import check_rate_limit
from app.config import settings
from app.evals.gold import load_gold_retrieval
from app.retrieval.eval_retrieval import recall_at_k


def test_gold_retrieval_loads():
    cases = load_gold_retrieval()
    assert len(cases) >= 8
    assert all(c["ticker"] and c["must_contain"] for c in cases)


@pytest.mark.asyncio
async def test_recall_at_k_mocked(monkeypatch):
    async def fake_retrieve(query, ticker, top_k=5):
        return [
            {"text": "filler", "section": "Risk Factors"},
            {"text": "other", "section": "Business"},
        ]

    monkeypatch.setattr(
        "app.retrieval.rerank.retrieve", fake_retrieve
    )
    score = await recall_at_k(
        [{"query": "q", "ticker": "AAPL", "must_contain": "Risk Factors"}],
        k=5,
    )
    assert score == 1.0


@pytest.mark.asyncio
async def test_reserve_quota_under_limit(monkeypatch):
    calls = {"n": 0}

    class Row:
        id = 42

    class FakeConn:
        async def execute(self, *a, **k):
            calls["n"] += 1

            class R:
                def first(self_inner):
                    return Row()

            return R()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class FakeEngine:
        def begin(self):
            return FakeConn()

    async def no_budget(_user_id):
        return None

    monkeypatch.setattr(limits, "engine", FakeEngine())
    monkeypatch.setattr(
        "app.api.cost_guards.assert_daily_budgets", no_budget
    )
    usage_id = await limits.reserve_quota("u1", "free")
    assert usage_id == 42
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_reserve_quota_over_limit(monkeypatch):
    class FakeConn:
        async def execute(self, *a, **k):
            class R:
                def first(self_inner):
                    return None

            return R()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class FakeEngine:
        def begin(self):
            return FakeConn()

    async def no_budget(_user_id):
        return None

    monkeypatch.setattr(limits, "engine", FakeEngine())
    monkeypatch.setattr(
        "app.api.cost_guards.assert_daily_budgets", no_budget
    )
    with pytest.raises(HTTPException) as ei:
        await limits.reserve_quota("u1", "free")
    assert ei.value.status_code == 402


def test_redis_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")

    def boom():
        raise HTTPException(503, "Rate limiter unavailable. Try again shortly.")

    monkeypatch.setattr(
        "app.api.ratelimit._get_redis",
        lambda: (_ for _ in ()).throw(
            HTTPException(503, "Rate limiter unavailable. Try again shortly.")
        ),
    )
    with pytest.raises(HTTPException) as ei:
        check_rate_limit("k", limit=10)
    assert ei.value.status_code == 503
