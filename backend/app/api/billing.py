import stripe
from fastapi import APIRouter, Request, Header, HTTPException
from sqlalchemy import text
from app.config import settings
from app.db import engine
stripe.api_key = settings.stripe_secret_key
router = APIRouter()

@router.post("/billing/checkout")
async def checkout(price_id: str, user_id: str):
    session = stripe.checkout.Session.create(
        mode="subscription", line_items=[{"price": price_id, "quantity": 1}],
        success_url="https://yourapp.com/success", cancel_url="https://yourapp.com/cancel",
        client_reference_id=user_id)
    return {"url": session.url}

@router.post("/billing/webhook")
async def webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature,
                                               settings.stripe_webhook_secret)
    except Exception:
        raise HTTPException(400, "bad signature")
    if event["type"] == "checkout.session.completed":
        s = event["data"]["object"]
        async with engine.begin() as conn:      # flip the user to 'pro'
            await conn.execute(text(
                "UPDATE users SET plan='pro' WHERE user_id=:u"),
                {"u": s["client_reference_id"]})
    return {"received": True}