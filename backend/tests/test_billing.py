from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import billing


@pytest.fixture(autouse=True)
def clear_stripe_env(monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_secret_key", "")
    monkeypatch.setattr(billing.settings, "stripe_webhook_secret", "")
    monkeypatch.setattr(billing.settings, "stripe_price_id", "")
    monkeypatch.setattr(billing.settings, "stripe_price_id_pro", "")
    monkeypatch.setattr(billing.settings, "stripe_price_id_team", "")
    monkeypatch.setattr(billing.settings, "frontend_url", "http://localhost:3000")


def test_status_flags(monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_secret_key", "sk_test")
    monkeypatch.setattr(billing.settings, "stripe_price_id_pro", "price_pro")
    out = {
        "configured": billing._stripe_key_ready(),
        "pro_price_configured": bool(billing._pro_price_id()),
        "team_price_configured": bool(billing._team_price_id()),
    }
    assert out["configured"] is True
    assert out["pro_price_configured"] is True
    assert out["team_price_configured"] is False


def test_plan_checkout_ready(monkeypatch):
    assert billing._plan_checkout_ready("free") is False
    monkeypatch.setattr(billing.settings, "stripe_secret_key", "sk_test")
    monkeypatch.setattr(billing.settings, "stripe_price_id_pro", "price_pro")
    monkeypatch.setattr(billing.settings, "stripe_price_id_team", "price_team")
    assert billing._plan_checkout_ready("pro") is True
    assert billing._plan_checkout_ready("team") is True


@pytest.mark.asyncio
async def test_checkout_rejects_without_stripe():
    with pytest.raises(HTTPException) as ei:
        await billing.checkout(billing.CheckoutBody(plan="pro"), "user-1")
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_checkout_rejects_pro_without_price(monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_secret_key", "sk_test")
    with pytest.raises(HTTPException) as ei:
        await billing.checkout(billing.CheckoutBody(plan="pro"), "user-1")
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_checkout_pro_creates_session(monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_secret_key", "sk_test")
    monkeypatch.setattr(billing.settings, "stripe_price_id_pro", "price_pro")

    created = {}

    class FakeSession:
        @staticmethod
        def create(**kwargs):
            created.update(kwargs)
            return SimpleNamespace(url="https://checkout.stripe.test/s")

    monkeypatch.setattr(billing.stripe, "api_key", None)
    monkeypatch.setattr(billing.stripe.checkout, "Session", FakeSession)

    out = await billing.checkout(billing.CheckoutBody(plan="pro"), "user-1")
    assert out["url"].startswith("https://checkout.stripe.test")
    assert out["plan"] == "pro"
    assert created["metadata"]["plan"] == "pro"
    assert created["client_reference_id"] == "user-1"
    assert created["line_items"][0]["price"] == "price_pro"


@pytest.mark.asyncio
async def test_checkout_team_creates_session(monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_secret_key", "sk_test")
    monkeypatch.setattr(billing.settings, "stripe_price_id_team", "price_team")

    class FakeSession:
        @staticmethod
        def create(**kwargs):
            return SimpleNamespace(url="https://checkout.stripe.test/t")

    monkeypatch.setattr(billing.stripe.checkout, "Session", FakeSession)
    out = await billing.checkout(billing.CheckoutBody(plan="team"), "user-1")
    assert out["plan"] == "team"


def test_resolve_checkout_plan_from_metadata():
    assert (
        billing._resolve_checkout_plan({"metadata": {"plan": "team"}}) == "team"
    )
    assert billing._resolve_checkout_plan({"metadata": {}}) is None


@pytest.mark.asyncio
async def test_apply_plan_writes_pro(monkeypatch):
    executed = {}

    class Conn:
        async def execute(self, stmt, params):
            executed["params"] = params

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class Engine:
        def begin(self):
            return Conn()

    monkeypatch.setattr(billing, "engine", Engine())
    await billing._apply_plan("user-9", "team")
    assert executed["params"] == {"u": "user-9", "p": "team"}


@pytest.mark.asyncio
async def test_apply_plan_ignores_free(monkeypatch):
    called = False

    class Engine:
        def begin(self):
            nonlocal called
            called = True
            raise AssertionError("should not touch DB for free")

    monkeypatch.setattr(billing, "engine", Engine())
    await billing._apply_plan("user-9", "unknown-plan")
    assert called is False
