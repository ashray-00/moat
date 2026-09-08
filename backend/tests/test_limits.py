import pytest
from fastapi import HTTPException

from app.api import limits


def test_normalize_unknown_plan():
    assert limits.normalize_plan(None) == "free"
    assert limits.normalize_plan("nope") == "free"
    assert limits.normalize_plan("pro") == "pro"


def test_plan_rpm_and_limits():
    assert limits.plan_rpm("free") == 10
    assert limits.plan_rpm("pro") == 60
    assert limits.plan_rpm("team") == 120
    assert limits.monthly_ask_limit("free") == 5
    assert limits.monthly_ask_limit("unknown") == 5


def test_list_public_plans():
    ids = {p["id"] for p in limits.list_public_plans()}
    assert ids == {"free", "pro", "team"}
    pro = next(p for p in limits.list_public_plans() if p["id"] == "pro")
    assert pro["checkout"] is True
    free = next(p for p in limits.list_public_plans() if p["id"] == "free")
    assert free["checkout"] is False


@pytest.mark.asyncio
async def test_enforce_quota_under_limit(monkeypatch):
    async def fake_usage(_user_id):
        return 1, "2026-09-01T00:00:00+00:00"

    monkeypatch.setattr(limits, "_month_usage", fake_usage)
    await limits.enforce_quota("user-1", "free")


@pytest.mark.asyncio
async def test_enforce_quota_over_limit(monkeypatch):
    async def fake_usage(_user_id):
        return 99, "2026-09-01T00:00:00+00:00"

    monkeypatch.setattr(limits, "_month_usage", fake_usage)
    with pytest.raises(HTTPException) as ei:
        await limits.enforce_quota("user-1", "free")
    assert ei.value.status_code == 402


@pytest.mark.asyncio
async def test_usage_snapshot(monkeypatch):
    async def fake_usage(_user_id):
        return 2, "2026-09-01T00:00:00+00:00"

    monkeypatch.setattr(limits, "_month_usage", fake_usage)
    snap = await limits.usage_snapshot("user-1", "free")
    assert snap["used"] == 2
    assert snap["limit"] == 5
    assert snap["remaining"] == 3
    assert snap["plan"] == "free"
    assert snap["rpm"] == 10
    assert snap["period_start"].startswith("2026-09-01")
