"""Unit tests for cost / signup abuse guards (no Redis)."""

import pytest
from fastapi import HTTPException

from app.api import cost_guards, signup_guards
from app.config import settings


def test_agent_allowed_on_free_by_default(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "agent_enabled", True)
    monkeypatch.setattr(settings, "free_agent_enabled", True)
    assert cost_guards.agent_allowed_for_plan("free") is True
    assert cost_guards.agent_allowed_for_plan("pro") is True
    cost_guards.assert_agent_allowed("free")


def test_agent_can_be_locked_to_paid(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "agent_enabled", True)
    monkeypatch.setattr(settings, "free_agent_enabled", False)
    assert cost_guards.agent_allowed_for_plan("free") is False
    assert cost_guards.agent_allowed_for_plan("pro") is True
    with pytest.raises(HTTPException) as ei:
        cost_guards.assert_agent_allowed("free")
    assert ei.value.status_code == 402


def test_agent_global_kill_switch(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "agent_enabled", False)
    monkeypatch.setattr(settings, "free_agent_enabled", True)
    assert cost_guards.agent_allowed_for_plan("pro") is False
    with pytest.raises(HTTPException) as ei:
        cost_guards.assert_agent_allowed("pro")
    assert ei.value.status_code == 503


def test_llm_kill_switch(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", False)
    with pytest.raises(HTTPException) as ei:
        cost_guards.assert_llm_enabled()
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_daily_budget_per_user(monkeypatch):
    monkeypatch.setattr(settings, "daily_cost_usd_per_user", 1.0)
    monkeypatch.setattr(settings, "daily_cost_usd_global", 0.0)

    async def fake_sum(*, user_id, since_sql):
        return 1.5 if user_id else 0.0

    monkeypatch.setattr(cost_guards, "_sum_cost_usd", fake_sum)
    with pytest.raises(HTTPException) as ei:
        await cost_guards.assert_daily_budgets("u1")
    assert ei.value.status_code == 402


@pytest.mark.asyncio
async def test_daily_budget_global(monkeypatch):
    monkeypatch.setattr(settings, "daily_cost_usd_per_user", 0.0)
    monkeypatch.setattr(settings, "daily_cost_usd_global", 10.0)

    async def fake_sum(*, user_id, since_sql):
        return 0.0 if user_id else 12.0

    monkeypatch.setattr(cost_guards, "_sum_cost_usd", fake_sum)
    with pytest.raises(HTTPException) as ei:
        await cost_guards.assert_daily_budgets("u1")
    assert ei.value.status_code == 503


def test_disposable_email_blocked(monkeypatch):
    monkeypatch.setattr(settings, "block_disposable_email", True)
    monkeypatch.setattr(settings, "blocked_email_domains", "")
    assert signup_guards.is_disposable_email("a@mailinator.com")
    with pytest.raises(HTTPException) as ei:
        signup_guards.assert_email_allowed("a@mailinator.com")
    assert ei.value.status_code == 400
    signup_guards.assert_email_allowed("ada@company.com")


def test_extra_blocked_domain(monkeypatch):
    monkeypatch.setattr(settings, "block_disposable_email", False)
    monkeypatch.setattr(settings, "blocked_email_domains", "evil.test")
    assert signup_guards.is_disposable_email("x@evil.test")


@pytest.mark.asyncio
async def test_signup_rate(monkeypatch):
    monkeypatch.setattr(settings, "max_signups_per_hour", 2)

    class Row:
        n = 2

    class FakeConn:
        async def execute(self, *a, **k):
            class R:
                def one(self_inner):
                    return Row()

            return R()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class FakeEngine:
        def begin(self):
            return FakeConn()

    monkeypatch.setattr(signup_guards, "engine", FakeEngine())
    with pytest.raises(HTTPException) as ei:
        await signup_guards.assert_signup_rate_ok()
    assert ei.value.status_code == 429
