"""Stripe Checkout integration for ClearVault.

Server-side fixed packages — frontend NEVER sends amount.
"""
import os
from typing import Optional

from emergentintegrations.payments.stripe.checkout import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CheckoutStatusResponse,
    StripeCheckout,
)

# Fixed packages — amount in float (Stripe rejects ints)
PACKAGES = {
    "desk_monthly": {
        "amount": 890.00,
        "currency": "usd",
        "label": "ClearVault Desk · per seat / month",
        "plan": "desk",
    },
    "desk_annual": {
        "amount": 8500.00,
        "currency": "usd",
        "label": "ClearVault Desk · annual (save $2,180)",
        "plan": "desk",
    },
}

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "sk_test_emergent")


def make_checkout(host_url: str) -> StripeCheckout:
    """Build a StripeCheckout bound to our /api/webhook/stripe endpoint."""
    base = host_url.rstrip("/")
    webhook_url = f"{base}/api/webhook/stripe"
    return StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)


def get_package(package_id: str) -> Optional[dict]:
    return PACKAGES.get(package_id)
