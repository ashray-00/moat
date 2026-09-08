from __future__ import annotations

import logging
from typing import Any, Literal

import stripe
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import RequiredUser, get_user_plan
from app.api.limits import PLANS, list_public_plans, normalize_plan, usage_snapshot
from app.config import settings
from app.db import engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

CheckoutPlan = Literal["pro", "team"]


def _stripe_key_ready() -> bool:
    return bool(settings.stripe_secret_key)


def _webhook_ready() -> bool:
    return bool(settings.stripe_secret_key and settings.stripe_webhook_secret)


def _pro_price_id() -> str:
    return (settings.stripe_price_id_pro or settings.stripe_price_id or "").strip()


def _team_price_id() -> str:
    return (settings.stripe_price_id_team or "").strip()


def _price_for_plan(plan: str) -> str:
    if plan == "pro":
        return _pro_price_id()
    if plan == "team":
        return _team_price_id()
    return ""


def _price_to_plan_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    pro = _pro_price_id()
    team = _team_price_id()
    if pro:
        mapping[pro] = "pro"
    if team:
        mapping[team] = "team"
    return mapping


def _plan_checkout_ready(plan_id: str) -> bool:
    cfg = PLANS.get(plan_id)
    if not cfg or not cfg.get("checkout"):
        return False
    return _stripe_key_ready() and bool(_price_for_plan(plan_id))


def _configure_stripe() -> None:
    stripe.api_key = settings.stripe_secret_key


async def get_billing_user(user_id: str) -> dict[str, Any]:
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT user_id, email, plan, stripe_customer_id, "
                    "stripe_subscription_id FROM users WHERE user_id=:u"
                ),
                {"u": user_id},
            )
        ).mappings().first()
    if not row:
        return {
            "user_id": user_id,
            "email": None,
            "plan": "free",
            "stripe_customer_id": None,
            "stripe_subscription_id": None,
        }
    return dict(row)


async def set_subscription(
    user_id: str,
    *,
    plan: str,
    customer_id: str | None,
    subscription_id: str | None,
) -> None:
    plan = normalize_plan(plan)
    if plan == "free":
        return
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (user_id, plan, stripe_customer_id, "
                "stripe_subscription_id, updated_at) "
                "VALUES (:u, :p, :c, :s, now()) "
                "ON CONFLICT (user_id) DO UPDATE SET "
                "plan=:p, "
                "stripe_customer_id=COALESCE(:c, users.stripe_customer_id), "
                "stripe_subscription_id=:s, "
                "updated_at=now()"
            ),
            {"u": user_id, "p": plan, "c": customer_id, "s": subscription_id},
        )
    if plan == "team":
        from app.orgs.store import ensure_team_org

        await ensure_team_org(user_id)


async def clear_subscription(user_id: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE users SET plan='free', stripe_subscription_id=NULL, "
                "updated_at=now() WHERE user_id=:u"
            ),
            {"u": user_id},
        )


async def find_user_id_by_customer(customer_id: str) -> str | None:
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT user_id FROM users WHERE stripe_customer_id=:c LIMIT 1"
                ),
                {"c": customer_id},
            )
        ).first()
    return row.user_id if row else None


async def find_user_id_by_subscription(subscription_id: str) -> str | None:
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT user_id FROM users WHERE stripe_subscription_id=:s "
                    "LIMIT 1"
                ),
                {"s": subscription_id},
            )
        ).first()
    return row.user_id if row else None


async def _claim_webhook_event(event_id: str) -> bool:
    """Return True if this event should be processed (first time seen)."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "INSERT INTO stripe_webhook_events (event_id) VALUES (:e) "
                "ON CONFLICT (event_id) DO NOTHING"
            ),
            {"e": event_id},
        )
    return (result.rowcount or 0) > 0


async def _release_webhook_event(event_id: str) -> None:
    """Allow Stripe to retry after a failed handler."""
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM stripe_webhook_events WHERE event_id=:e"),
            {"e": event_id},
        )

# Back-compat name used by older tests
async def _apply_plan(user_id: str, plan: str) -> None:
    await set_subscription(
        user_id, plan=plan, customer_id=None, subscription_id=None
    )


class CheckoutBody(BaseModel):
    plan: CheckoutPlan = Field(description="Paid plan to subscribe to")


@router.get("/me")
async def billing_me(user_id: RequiredUser):
    bu = await get_billing_user(user_id)
    plan = normalize_plan(bu.get("plan") or await get_user_plan(user_id))
    snap = await usage_snapshot(user_id, plan)
    plans = []
    for p in list_public_plans():
        plans.append(
            {
                **p,
                "checkout_ready": _plan_checkout_ready(p["id"]),
                "current": p["id"] == snap["plan"],
            }
        )
    has_customer = bool(bu.get("stripe_customer_id"))
    has_sub = bool(bu.get("stripe_subscription_id")) and snap["plan"] != "free"
    return {
        **snap,
        "stripe_checkout_available": any(p["checkout_ready"] for p in plans),
        "has_stripe_customer": has_customer,
        "has_active_subscription": has_sub,
        "plans": plans,
    }


@router.post("/checkout")
async def checkout(body: CheckoutBody, user_id: RequiredUser):
    plan = body.plan
    if plan not in PLANS or not PLANS[plan].get("checkout"):
        raise HTTPException(400, f"Plan '{plan}' is not available for checkout")

    if not _stripe_key_ready():
        raise HTTPException(
            503,
            "Stripe is not configured. Set STRIPE_SECRET_KEY to enable checkout.",
        )

    price_id = _price_for_plan(plan)
    if not price_id:
        env_name = (
            "STRIPE_PRICE_ID_PRO (or STRIPE_PRICE_ID)"
            if plan == "pro"
            else "STRIPE_PRICE_ID_TEAM"
        )
        raise HTTPException(503, f"Billing not configured for {plan}. Set {env_name}.")

    bu = await get_billing_user(user_id)
    prev_sub = bu.get("stripe_subscription_id") or ""
    meta = {"plan": plan, "user_id": user_id}
    if prev_sub:
        meta["previous_subscription_id"] = prev_sub

    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{settings.frontend_url.rstrip('/')}/billing/success",
        "cancel_url": f"{settings.frontend_url.rstrip('/')}/billing/cancel",
        "client_reference_id": user_id,
        "metadata": meta,
        "subscription_data": {"metadata": {"plan": plan, "user_id": user_id}},
    }
    if bu.get("stripe_customer_id"):
        params["customer"] = bu["stripe_customer_id"]
    elif bu.get("email"):
        params["customer_email"] = bu["email"]

    _configure_stripe()
    try:
        session = stripe.checkout.Session.create(**params)
    except stripe.error.StripeError as exc:
        logger.warning("stripe checkout failed: %s", type(exc).__name__)
        raise HTTPException(502, "Stripe checkout failed. Try again shortly.") from exc

    return {"url": session.url, "plan": plan}


@router.post("/portal")
async def billing_portal(user_id: RequiredUser):
    if not _stripe_key_ready():
        raise HTTPException(503, "Stripe is not configured")
    bu = await get_billing_user(user_id)
    customer_id = bu.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(400, "No billing account yet. Upgrade to a paid plan first.")

    _configure_stripe()
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{settings.frontend_url.rstrip('/')}/",
        )
    except stripe.error.StripeError as exc:
        logger.warning("stripe portal failed: %s", type(exc).__name__)
        raise HTTPException(502, "Could not open billing portal.") from exc
    return {"url": session.url}


def _resolve_checkout_plan(session_obj: dict) -> str | None:
    meta = session_obj.get("metadata") or {}
    meta_plan = meta.get("plan")
    if meta_plan in ("pro", "team"):
        return meta_plan

    price_map = _price_to_plan_map()
    for item in session_obj.get("line_items", {}).get("data", []) or []:
        price = (item.get("price") or {}).get("id")
        if price in price_map:
            return price_map[price]
    return None


def _plan_from_subscription(sub: dict) -> str | None:
    meta = sub.get("metadata") or {}
    if meta.get("plan") in ("pro", "team"):
        return meta["plan"]
    price_map = _price_to_plan_map()
    items = (sub.get("items") or {}).get("data") or []
    for item in items:
        price = (item.get("price") or {}).get("id")
        if price in price_map:
            return price_map[price]
    return None


def _cancel_subscription_safe(subscription_id: str) -> None:
    try:
        stripe.Subscription.delete(subscription_id)
    except stripe.error.InvalidRequestError:
        # Already canceled / missing — fine on webhook retries.
        pass
    except stripe.error.StripeError as exc:
        logger.warning(
            "failed canceling prior subscription %s: %s",
            subscription_id,
            type(exc).__name__,
        )


async def _handle_checkout_completed(session_obj: dict) -> None:
    uid = session_obj.get("client_reference_id") or (
        (session_obj.get("metadata") or {}).get("user_id")
    )
    plan = _resolve_checkout_plan(session_obj)
    if not uid or not plan:
        return

    customer_id = session_obj.get("customer")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    subscription_id = session_obj.get("subscription")
    if isinstance(subscription_id, dict):
        subscription_id = subscription_id.get("id")

    await set_subscription(
        uid,
        plan=plan,
        customer_id=str(customer_id) if customer_id else None,
        subscription_id=str(subscription_id) if subscription_id else None,
    )

    prev = (session_obj.get("metadata") or {}).get("previous_subscription_id")
    if prev and subscription_id and prev != subscription_id:
        _configure_stripe()
        _cancel_subscription_safe(str(prev))


async def _handle_subscription_updated(sub: dict) -> None:
    plan = _plan_from_subscription(sub)
    if not plan:
        return
    customer_id = sub.get("customer")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    sub_id = sub.get("id")
    uid = (sub.get("metadata") or {}).get("user_id")
    if not uid and customer_id:
        uid = await find_user_id_by_customer(str(customer_id))
    if not uid:
        return
    status = sub.get("status")
    if status in ("canceled", "unpaid", "incomplete_expired"):
        await clear_subscription(uid)
        return
    await set_subscription(
        uid,
        plan=plan,
        customer_id=str(customer_id) if customer_id else None,
        subscription_id=str(sub_id) if sub_id else None,
    )


async def _handle_subscription_deleted(sub: dict) -> None:
    sub_id = sub.get("id")
    customer_id = sub.get("customer")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    uid = (sub.get("metadata") or {}).get("user_id")
    if not uid and sub_id:
        uid = await find_user_id_by_subscription(str(sub_id))
    if not uid and customer_id:
        uid = await find_user_id_by_customer(str(customer_id))
    if uid:
        await clear_subscription(uid)


@router.post("/webhook")
async def webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
):
    if not _webhook_ready():
        raise HTTPException(503, "Stripe webhook is not configured")
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except Exception:
        raise HTTPException(400, "bad signature")

    event_id = event.get("id") or ""
    if event_id and not await _claim_webhook_event(event_id):
        return {"received": True, "duplicate": True}

    etype = event["type"]
    obj = event["data"]["object"]
    try:
        if etype == "checkout.session.completed":
            await _handle_checkout_completed(obj)
        elif etype == "customer.subscription.updated":
            await _handle_subscription_updated(obj)
        elif etype == "customer.subscription.deleted":
            await _handle_subscription_deleted(obj)
    except Exception:
        if event_id:
            await _release_webhook_event(event_id)
        logger.exception("stripe webhook handler failed type=%s", etype)
        raise HTTPException(500, "webhook handler failed")
    return {"received": True}


@router.get("/status")
async def billing_status(_user_id: RequiredUser):
    return {
        "configured": _stripe_key_ready(),
        "webhook_configured": _webhook_ready(),
        "pro_price_configured": bool(_pro_price_id()),
        "team_price_configured": bool(_team_price_id()),
        "price_id_set": bool(_pro_price_id()),
    }
