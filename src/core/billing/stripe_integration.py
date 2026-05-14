"""
Zenic-Agents Billing — Stripe Integration

Wraps the Stripe Python SDK for customer creation, subscription management,
portal sessions, invoice listing, and webhook verification.

If the ``stripe`` package is not installed, every method returns a safe
default value and logs a warning so the rest of the platform keeps running.

This module provides backward compatibility for E2E tests that patch
``src.core.billing.stripe_integration._stripe`` at the module level.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from .types import InvoiceRecord, PlanType, STRIPE_PRICE_IDS

logger = logging.getLogger(__name__)

# Lazily loaded stripe module reference
_stripe: Any = None
_stripe_available: bool = False


def _ensure_stripe() -> bool:
    """Import stripe once and set the API key from the environment."""
    global _stripe, _stripe_available
    if _stripe_available:
        return True
    try:
        import stripe as _s  # type: ignore[import-untyped]
        _stripe = _s
        api_key = os.environ.get("STRIPE_SECRET_KEY", "")
        if api_key:
            _stripe.api_key = api_key
        _stripe_available = True
        return True
    except ImportError:
        logger.warning("StripeIntegration: 'stripe' package not installed — using stubs")
        return False


def _resolve_price_id(plan: PlanType) -> str:
    """Return the Stripe price ID for a plan, checking env vars first."""
    env_map = {
        PlanType.STARTER: "STRIPE_STARTER_PRICE_ID",
        PlanType.BUSINESS: "STRIPE_BUSINESS_PRICE_ID",
        PlanType.ENTERPRISE: "STRIPE_ENTERPRISE_PRICE_ID",
    }
    env_key = env_map.get(plan)
    if env_key:
        val = os.environ.get(env_key, "")
        if val:
            return val
    return STRIPE_PRICE_IDS.get(plan.value, "")


class StripeIntegration:
    """Stripe API wrapper with safe fallbacks.

    All public methods catch exceptions and return sensible defaults so
    that a missing or misconfigured Stripe account never crashes the app.
    """

    def __init__(self) -> None:
        self._available = _ensure_stripe()
        self._webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        # Internal reference to StripeClient for aiohttp-based calls
        from .stripe_client import StripeClient as _StripeClient
        self._client = _StripeClient(
            api_key=os.environ.get("STRIPE_SECRET_KEY", ""),
            webhook_secret=self._webhook_secret,
        )
        if self._available:
            logger.info("StripeIntegration: initialized with API key")
        else:
            logger.info("StripeIntegration: running in stub mode (no stripe SDK)")

    # ── Customers ───────────────────────────────────────

    def create_customer(self, tenant_id: str, email: str) -> str:
        """Create a Stripe customer and return the customer ID.

        Returns empty string on failure.
        """
        if not self._available:
            logger.debug("StripeIntegration: create_customer stub — returning empty")
            return ""
        try:
            customer = _stripe.Customer.create(
                email=email,
                metadata={"tenant_id": tenant_id},
            )
            logger.info("StripeIntegration: customer %s created for tenant '%s'",
                        customer.id, tenant_id)
            return str(customer.id)
        except Exception as exc:
            logger.error("StripeIntegration: create_customer failed: %s", exc)
            return ""

    # ── Subscriptions ───────────────────────────────────

    def create_subscription(
        self,
        customer_id: str,
        plan_type: PlanType,
    ) -> str:
        """Create a subscription for an existing customer.

        Returns the Stripe subscription ID, or empty string on failure.
        """
        if not self._available:
            return ""
        price_id = _resolve_price_id(plan_type)
        if not price_id:
            logger.error("StripeIntegration: no price ID for plan %s", plan_type.value)
            return ""
        try:
            sub = _stripe.Subscription.create(
                customer=customer_id,
                items=[{"price": price_id, "quantity": 1}],
                metadata={"plan_type": plan_type.value},
            )
            logger.info("StripeIntegration: subscription %s created (%s)",
                        sub.id, plan_type.value)
            return str(sub.id)
        except Exception as exc:
            logger.error("StripeIntegration: create_subscription failed: %s", exc)
            return ""

    def cancel_subscription(self, subscription_id: str) -> bool:
        """Cancel a subscription immediately.

        Returns True on success, False otherwise.
        """
        if not self._available:
            return False
        try:
            _stripe.Subscription.delete(subscription_id)
            logger.info("StripeIntegration: subscription %s cancelled", subscription_id)
            return True
        except Exception as exc:
            logger.error("StripeIntegration: cancel_subscription failed: %s", exc)
            return False

    def update_subscription(
        self,
        subscription_id: str,
        new_plan: PlanType,
    ) -> bool:
        """Change the plan on an existing subscription.

        Returns True on success.
        """
        if not self._available:
            return False
        price_id = _resolve_price_id(new_plan)
        if not price_id:
            logger.error("StripeIntegration: no price ID for plan %s", new_plan.value)
            return False
        try:
            sub = _stripe.Subscription.retrieve(subscription_id)
            # Replace the first item with the new price
            item_id = sub["items"]["data"][0]["id"]
            _stripe.Subscription.modify(
                subscription_id,
                items=[{"id": item_id, "price": price_id}],
                metadata={"plan_type": new_plan.value},
            )
            logger.info("StripeIntegration: subscription %s updated to %s",
                        subscription_id, new_plan.value)
            return True
        except Exception as exc:
            logger.error("StripeIntegration: update_subscription failed: %s", exc)
            return False

    # ── Customer Portal ─────────────────────────────────

    def get_customer_portal_url(self, customer_id: str) -> str:
        """Create a Stripe Customer Portal session and return its URL.

        Returns empty string on failure.
        """
        if not self._available:
            return ""
        try:
            session = _stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=os.environ.get(
                    "STRIPE_PORTAL_RETURN_URL", "http://localhost:5000/app/billing"
                ),
            )
            return str(session.url)
        except Exception as exc:
            logger.error("StripeIntegration: portal session failed: %s", exc)
            return ""

    # ── Invoices ────────────────────────────────────────

    def list_invoices(
        self,
        customer_id: str,
        limit: int = 10,
    ) -> List[InvoiceRecord]:
        """List recent invoices for a customer.

        Returns an empty list on failure.
        """
        if not self._available:
            return []
        try:
            invoices = _stripe.Invoice.list(
                customer=customer_id,
                limit=limit,
            )
            results: List[InvoiceRecord] = []
            for inv in invoices.auto_paging_iter():
                results.append(
                    InvoiceRecord(
                        tenant_id="",  # filled by caller if needed
                        invoice_id=inv.id,
                        amount_cents=inv.amount_due or 0,
                        status=inv.status or "draft",
                        created_at=inv.created,
                        pdf_url=inv.invoice_pdf or "",
                    )
                )
            return results
        except Exception as exc:
            logger.error("StripeIntegration: list_invoices failed: %s", exc)
            return []

    # ── Webhook Verification ────────────────────────────

    def verify_webhook_signature(
        self,
        payload: str,
        sig_header: str,
    ) -> Optional[Dict[str, Any]]:
        """Verify and parse a Stripe webhook payload.

        Returns the parsed event dict, or None on verification failure.
        """
        if not self._available:
            logger.warning("StripeIntegration: webhook verify skipped — no SDK")
            return None
        if not self._webhook_secret:
            logger.warning("StripeIntegration: STRIPE_WEBHOOK_SECRET not set")
            return None
        try:
            event = _stripe.Webhook.construct_event(
                payload, sig_header, self._webhook_secret,
            )
            return dict(event)
        except _stripe.error.SignatureVerificationError as exc:
            logger.error("StripeIntegration: webhook signature invalid: %s", exc)
            return None
        except Exception as exc:
            logger.error("StripeIntegration: webhook verify failed: %s", exc)
            return None
