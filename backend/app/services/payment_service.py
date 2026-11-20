import uuid
from typing import Any, Dict

import httpx
from fastapi import HTTPException

from app.config import settings


def create_checkout_session(amount: float, customer_email: str) -> Dict[str, Any]:
    amount_in_paise = max(1, int(round(amount * 100)))

    if settings.PAYMENT_PROVIDER == "sandbox":
        reference = f"sandbox_{uuid.uuid4().hex}"
        return {
            "provider": "sandbox",
            "reference": reference,
            "status": "ready",
            "checkout_url": None,
            "message": "Sandbox payment is ready. No real money will be charged.",
        }

    if settings.PAYMENT_PROVIDER == "stripe":
        if not settings.STRIPE_SECRET_KEY:
            raise HTTPException(status_code=503, detail="Stripe is configured but STRIPE_SECRET_KEY is missing")
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(
                    "https://api.stripe.com/v1/checkout/sessions",
                    auth=(settings.STRIPE_SECRET_KEY, ""),
                    data={
                        "mode": "payment",
                        "success_url": f"{settings.PUBLIC_BASE_URL}/pages/cart.html?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
                        "cancel_url": f"{settings.PUBLIC_BASE_URL}/pages/cart.html?payment=cancelled",
                        "customer_email": customer_email,
                        "line_items[0][quantity]": "1",
                        "line_items[0][price_data][currency]": "inr",
                        "line_items[0][price_data][unit_amount]": str(amount_in_paise),
                        "line_items[0][price_data][product_data][name]": "AI Foodie order",
                    },
                )
                response.raise_for_status()
                session = response.json()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=502, detail=f"Payment provider unavailable: {type(exc).__name__}") from exc

        return {
            "provider": "stripe",
            "reference": session["id"],
            "status": "ready",
            "checkout_url": session["url"],
            "message": "Redirecting to Stripe Checkout.",
        }

    raise HTTPException(status_code=503, detail=f"Unsupported PAYMENT_PROVIDER: {settings.PAYMENT_PROVIDER}")


def verify_payment(reference: str) -> bool:
    if not reference:
        return False
    if settings.PAYMENT_PROVIDER == "sandbox":
        return reference.startswith("sandbox_")
    if settings.PAYMENT_PROVIDER == "stripe":
        if not settings.STRIPE_SECRET_KEY:
            return False
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(
                    f"https://api.stripe.com/v1/checkout/sessions/{reference}",
                    auth=(settings.STRIPE_SECRET_KEY, ""),
                )
                response.raise_for_status()
                return response.json().get("payment_status") == "paid"
        except httpx.HTTPError:
            return False
    return False
