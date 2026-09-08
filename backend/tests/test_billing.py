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

    async def fake_billing_user(user_id: str):
        return {
            "user_id": user_id,
            "email": "u@example.com",
            "plan": "free",
            "stripe_customer_id": None,
            "stripe_subscription_id": None,
        }

    monkeypatch.setattr(billing, "get_billing_user", fake_billing_user)


def test_status_flags(monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_secret_key", "sk_test")
    monkeypatch.setattr(billing.settings, "stripe_price_id_pro", "price_pro")
    assert billing._stripe_key_ready() is True
    assert bool(billing._pro_price_id()) is True
    assert bool(billing._team_price_id()) is False


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

    monkeypatch.setattr(billing.stripe.checkout, "Session", FakeSession)

    out = await billing.checkout(billing.CheckoutBody(plan="pro"), "user-1")
    assert out["url"].startswith("https://checkout.stripe.test")
    assert out["plan"] == "pro"
    assert created["metadata"]["plan"] == "pro"
    assert created["client_reference_id"] == "user-1"
    assert created["customer_email"] == "u@example.com"
    assert created["subscription_data"]["metadata"]["plan"] == "pro"
    assert "customer" not in created


@pytest.mark.asyncio
async def test_checkout_reuses_customer(monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_secret_key", "sk_test")
    monkeypatch.setattr(billing.settings, "stripe_price_id_team", "price_team")

    async def with_customer(user_id: str):
        return {
            "user_id": user_id,
            "email": "u@example.com",
            "plan": "pro",
            "stripe_customer_id": "cus_1",
            "stripe_subscription_id": "sub_old",
        }

    monkeypatch.setattr(billing, "get_billing_user", with_customer)
    created = {}

    class FakeSession:
        @staticmethod
        def create(**kwargs):
            created.update(kwargs)
            return SimpleNamespace(url="https://checkout.stripe.test/s")

    monkeypatch.setattr(billing.stripe.checkout, "Session", FakeSession)
    await billing.checkout(billing.CheckoutBody(plan="team"), "user-1")
    assert created["customer"] == "cus_1"
    assert "customer_email" not in created
    assert created["metadata"]["previous_subscription_id"] == "sub_old"


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
    assert billing._resolve_checkout_plan({"metadata": {"plan": "team"}}) == "team"
    assert billing._resolve_checkout_plan({"metadata": {}}) is None


@pytest.mark.asyncio
async def test_apply_plan_writes_pro(monkeypatch):
    executed = {}

    class Conn:
        async def execute(self, stmt, params):
            executed["params"] = params
            return SimpleNamespace(rowcount=1)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class Engine:
        def begin(self):
            return Conn()

    async def fake_ensure_team_org(owner_user_id: str, name: str | None = None):
        executed["org"] = owner_user_id
        return {
            "org_id": "org-1",
            "name": name or "Team",
            "owner_user_id": owner_user_id,
            "role": "owner",
        }

    monkeypatch.setattr(billing, "engine", Engine())
    # team plan calls ensure_team_org (imported at call time from app.orgs.store)
    monkeypatch.setattr(
        "app.orgs.store.ensure_team_org", fake_ensure_team_org
    )
    await billing._apply_plan("user-9", "team")
    assert executed["params"]["u"] == "user-9"
    assert executed["params"]["p"] == "team"
    assert executed["org"] == "user-9"


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


@pytest.mark.asyncio
async def test_portal_requires_customer(monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_secret_key", "sk_test")
    with pytest.raises(HTTPException) as ei:
        await billing.billing_portal("user-1")
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_portal_returns_url(monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_secret_key", "sk_test")

    async def with_customer(user_id: str):
        return {
            "user_id": user_id,
            "email": "u@example.com",
            "plan": "pro",
            "stripe_customer_id": "cus_1",
            "stripe_subscription_id": "sub_1",
        }

    monkeypatch.setattr(billing, "get_billing_user", with_customer)

    class FakePortal:
        @staticmethod
        def create(**kwargs):
            return SimpleNamespace(url="https://billing.stripe.test/p")

    monkeypatch.setattr(billing.stripe.billing_portal, "Session", FakePortal)
    out = await billing.billing_portal("user-1")
    assert out["url"].startswith("https://billing.stripe.test")


@pytest.mark.asyncio
async def test_handle_checkout_cancels_previous(monkeypatch):
    calls = {"set": None, "cancel": []}

    async def fake_set(user_id, *, plan, customer_id, subscription_id):
        calls["set"] = {
            "user_id": user_id,
            "plan": plan,
            "customer_id": customer_id,
            "subscription_id": subscription_id,
        }

    def fake_cancel(sub_id):
        calls["cancel"].append(sub_id)

    monkeypatch.setattr(billing, "set_subscription", fake_set)
    monkeypatch.setattr(billing, "_cancel_subscription_safe", fake_cancel)

    await billing._handle_checkout_completed(
        {
            "client_reference_id": "user-1",
            "customer": "cus_1",
            "subscription": "sub_new",
            "metadata": {
                "plan": "team",
                "previous_subscription_id": "sub_old",
            },
        }
    )
    assert calls["set"]["plan"] == "team"
    assert calls["set"]["subscription_id"] == "sub_new"
    assert calls["cancel"] == ["sub_old"]


@pytest.mark.asyncio
async def test_handle_subscription_deleted(monkeypatch):
    cleared = []

    async def fake_clear(uid):
        cleared.append(uid)

    async def fake_find(sub_id):
        return "user-7"

    monkeypatch.setattr(billing, "clear_subscription", fake_clear)
    monkeypatch.setattr(billing, "find_user_id_by_subscription", fake_find)
    await billing._handle_subscription_deleted({"id": "sub_x", "customer": "cus"})
    assert cleared == ["user-7"]
