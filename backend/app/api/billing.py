from __future__ import annotations

from typing import Literal

import stripe
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import RequiredUser, get_user_plan
from app.api.limits import PLANS, list_public_plans, normalize_plan, usage_snapshot
from app.config import settings
from app.db import engine

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


class CheckoutBody(BaseModel):
    plan: CheckoutPlan = Field(description="Paid plan to subscribe to")


@router.get("/me")
async def billing_me(user_id: RequiredUser):
    plan = await get_user_plan(user_id)
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
    return {
        **snap,
        "stripe_checkout_available": any(p["checkout_ready"] for p in plans),
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

    stripe.api_key = settings.stripe_secret_key
    base = settings.frontend_url.rstrip("/")
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{base}/billing/success",
        cancel_url=f"{base}/billing/cancel",
        client_reference_id=user_id,
        metadata={"plan": plan, "user_id": user_id},
    )
    return {"url": session.url, "plan": plan}


async def _apply_plan(user_id: str, plan: str) -> None:
    plan = normalize_plan(plan)
    if plan == "free":
        return
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (user_id, plan) VALUES (:u, :p) "
                "ON CONFLICT (user_id) DO UPDATE SET plan=:p, updated_at=now()"
            ),
            {"u": user_id, "p": plan},
        )


def _resolve_checkout_plan(session_obj: dict) -> str | None:
    meta = session_obj.get("metadata") or {}
    meta_plan = meta.get("plan")
    if meta_plan in ("pro", "team"):
        return meta_plan

    # Fallback: match line item price if present on expanded sessions (often absent).
    price_map = _price_to_plan_map()
    for item in session_obj.get("line_items", {}).get("data", []) or []:
        price = (item.get("price") or {}).get("id")
        if price in price_map:
            return price_map[price]

    # Some payloads only have a single price in display items / amount details — skip.
    return None


@router.post("/webhook")
async def webhook(request: Request, stripe_signature: str | None = Header(default=None)):
    if not _webhook_ready():
        raise HTTPException(503, "Stripe webhook is not configured")
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except Exception:
        raise HTTPException(400, "bad signature")

    if event["type"] == "checkout.session.completed":
        s = event["data"]["object"]
        uid = s.get("client_reference_id") or (s.get("metadata") or {}).get("user_id")
        plan = _resolve_checkout_plan(s)
        if uid and plan:
            await _apply_plan(uid, plan)
    return {"received": True}


@router.get("/status")
async def billing_status():
    return {
        "configured": _stripe_key_ready(),
        "webhook_configured": _webhook_ready(),
        "pro_price_configured": bool(_pro_price_id()),
        "team_price_configured": bool(_team_price_id()),
        # Back-compat for older clients
        "price_id_set": bool(_pro_price_id()),
    }
