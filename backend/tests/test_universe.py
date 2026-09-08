import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api import universe as universe_api
from app.ingest.universe import default_universe
from app.universe import store as ustore


@pytest.mark.asyncio
async def test_get_universe_free(monkeypatch):
    async def fake_plan(_uid):
        return "free"

    async def fake_adds(_uid):
        return []

    monkeypatch.setattr(universe_api, "get_user_plan", fake_plan)
    monkeypatch.setattr(ustore, "list_user_adds", fake_adds)
    out = await universe_api.get_universe("u1")
    assert out["default"] == default_universe()
    assert out["can_modify"] is False
    assert out["limit"] == 0
    assert out["used"] == 0


@pytest.mark.asyncio
async def test_free_cannot_add(monkeypatch):
    async def fake_plan(_uid):
        return "free"

    monkeypatch.setattr(universe_api, "get_user_plan", fake_plan)
    with pytest.raises(HTTPException) as ei:
        await universe_api.add_ticker(
            universe_api.AddTickerBody(ticker="CRM"),
            "u1",
            BackgroundTasks(),
        )
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_cannot_remove_default(monkeypatch):
    async def fake_plan(_uid):
        return "pro"

    monkeypatch.setattr(universe_api, "get_user_plan", fake_plan)
    with pytest.raises(HTTPException) as ei:
        await universe_api.remove_ticker("AAPL", "u1")
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_add_fast_path_skips_ingest(monkeypatch):
    async def fake_plan(_uid):
        return "pro"

    calls = {"ingest": 0, "upsert": None}

    async def fake_get(_u, _t):
        return None

    async def fake_count(_u):
        return 0

    async def fake_ready(_t):
        return True

    async def fake_upsert(u, t, *, status, error=None):
        calls["upsert"] = status
        return {"ticker": t, "status": status}

    async def fake_run(u, t):
        calls["ingest"] += 1

    monkeypatch.setattr(universe_api, "get_user_plan", fake_plan)
    monkeypatch.setattr(ustore, "get_user_add", fake_get)
    monkeypatch.setattr(ustore, "count_user_adds", fake_count)
    monkeypatch.setattr(ustore, "company_ready", fake_ready)
    monkeypatch.setattr(ustore, "upsert_user_add", fake_upsert)
    monkeypatch.setattr(ustore, "run_ingest_job", fake_run)

    bg = BackgroundTasks()
    out = await universe_api.add_ticker(
        universe_api.AddTickerBody(ticker="crm"),
        "u1",
        bg,
    )
    assert out["status"] == "ready"
    assert out["started_ingest"] is False
    assert calls["ingest"] == 0
    assert len(bg.tasks) == 0


@pytest.mark.asyncio
async def test_add_slow_path_queues_ingest(monkeypatch):
    async def fake_plan(_uid):
        return "pro"

    async def fake_get(_u, _t):
        return None

    async def fake_count(_u):
        return 0

    async def fake_ready(_t):
        return False

    async def fake_inflight(_u):
        return False

    async def fake_upsert(u, t, *, status, error=None):
        return {"ticker": t, "status": status}

    monkeypatch.setattr(universe_api, "get_user_plan", fake_plan)
    monkeypatch.setattr(ustore, "get_user_add", fake_get)
    monkeypatch.setattr(ustore, "count_user_adds", fake_count)
    monkeypatch.setattr(ustore, "company_ready", fake_ready)
    monkeypatch.setattr(ustore, "has_in_flight_ingest", fake_inflight)
    monkeypatch.setattr(ustore, "upsert_user_add", fake_upsert)
    monkeypatch.setattr(
        universe_api, "check_rate_limit", lambda *a, **k: None
    )

    bg = BackgroundTasks()
    out = await universe_api.add_ticker(
        universe_api.AddTickerBody(ticker="SHOP"),
        "u1",
        bg,
    )
    assert out["status"] == "pending"
    assert out["started_ingest"] is True
    assert len(bg.tasks) == 1


@pytest.mark.asyncio
async def test_add_cap(monkeypatch):
    async def fake_plan(_uid):
        return "pro"

    async def fake_get(_u, _t):
        return None

    async def fake_count(_u):
        return 10

    monkeypatch.setattr(universe_api, "get_user_plan", fake_plan)
    monkeypatch.setattr(ustore, "get_user_add", fake_get)
    monkeypatch.setattr(ustore, "count_user_adds", fake_count)

    with pytest.raises(HTTPException) as ei:
        await universe_api.add_ticker(
            universe_api.AddTickerBody(ticker="SHOP"),
            "u1",
            BackgroundTasks(),
        )
    assert ei.value.status_code == 403
    assert "limit" in str(ei.value.detail).lower()


@pytest.mark.asyncio
async def test_run_ingest_job_marks_ready(monkeypatch):
    calls = {"upsert": [], "mark": []}

    async def fake_upsert(u, t, *, status, error=None):
        calls["upsert"].append(status)
        return {"ticker": t, "status": status}

    async def fake_ready(_t):
        return True

    async def fake_mark(t, *, status, error=None):
        calls["mark"].append(status)

    async def fake_enqueue(_t):
        return None, False

    monkeypatch.setattr(ustore, "upsert_user_add", fake_upsert)
    monkeypatch.setattr(ustore, "company_ready", fake_ready)
    monkeypatch.setattr(ustore, "mark_waiting_users", fake_mark)
    monkeypatch.setattr(ustore, "enqueue_ingest_job", fake_enqueue)

    await ustore.run_ingest_job("u1", "SHOP")
    assert calls["upsert"] == ["pending"]
    assert calls["mark"] == ["ready"]


@pytest.mark.asyncio
async def test_effective_universe(monkeypatch):
    async def fake_adds(_u):
        return [
            {"ticker": "CRM", "status": "ready"},
            {"ticker": "SHOP", "status": "pending"},
        ]

    monkeypatch.setattr(ustore, "list_user_adds", fake_adds)
    got = await ustore.effective_universe("u1")
    assert "AAPL" in got
    assert "CRM" in got
    assert "SHOP" not in got
