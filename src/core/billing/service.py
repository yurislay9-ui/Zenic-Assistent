"""
BillingService — facade that unifies TrialManager, SubscriptionManager,
StripeClient, and WebhookHandler into a single service.

This is the main entry point used by the HTMX routes and the
``get_billing_service()`` module-level helper.

The BillingService is designed as a lazy singleton (via ``get_billing_service``)
so that all parts of the app share the same instance.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from .types import (
    BillingEvent,
    BillingPlan,
    BillingRecord,
    PLAN_LIMITS,
    PlanType,
    SubscriptionStatus,
    TRIAL_DURATION_DAYS,
    TrialInfo,
    UsageRecord,
)
from .stripe_client import StripeClient, StripeIntegration
from .subscription_manager import SubscriptionManager
from .trial_manager import TrialManager
from .webhook_handler import BillingWebhookHandler, WebhookHandler

logger = logging.getLogger(__name__)


class BillingService:
    """Unified billing service facade.

    Provides a single API for all billing operations:
      - Trial management (start, check, expire, extend)
      - Subscription lifecycle (activate, cancel, change plan)
      - Feature access checking
      - Usage tracking
      - Webhook processing
      - Stripe integration

    Args:
        db_path: Path to the SQLite database.
        stripe_api_key: Stripe secret key (empty = dev mode).
        stripe_webhook_secret: Stripe webhook signing secret.
    """

    def __init__(
        self,
        db_path: str = "billing.db",
        stripe_api_key: str = "",
        stripe_webhook_secret: str = "",
    ) -> None:
        self._db_path = db_path
        self._lock = threading.RLock()

        # Initialize Stripe client
        api_key = stripe_api_key or os.environ.get("STRIPE_SECRET_KEY", "")
        wh_secret = stripe_webhook_secret or os.environ.get("STRIPE_WEBHOOK_SECRET", "")

        self._stripe_client: Optional[StripeClient] = None
        self._stripe_integration: Optional[StripeIntegration] = None

        if api_key:
            self._stripe_client = StripeClient(api_key=api_key, webhook_secret=wh_secret)
            self._stripe_integration = StripeIntegration(api_key=api_key, webhook_secret=wh_secret)

        # Initialize managers (shared DB path)
        self._trial_manager = TrialManager(db_path=db_path)
        self._subscription_manager = SubscriptionManager(
            stripe_client=self._stripe_client,
            db_path=db_path,
        )

        # Initialize webhook handler
        self._webhook_handler = BillingWebhookHandler(
            subscription_manager=self._subscription_manager,
            stripe_client=self._stripe_client,
        )

        logger.info("BillingService: initialized (db=%s, stripe=%s)", db_path, "yes" if api_key else "no")

    # ── Trial management ───────────────────────────────────

    def start_trial(self, tenant_id: str) -> BillingRecord:
        """Start a 14-day trial for a tenant."""
        return self._trial_manager.start_trial(tenant_id)

    def get_trial_info(self, tenant_id: str) -> Optional[TrialInfo]:
        """Get trial info for a tenant."""
        return self._trial_manager.get_trial_info(tenant_id)

    def is_trial_active(self, tenant_id: str) -> bool:
        """Check if a tenant's trial is still active."""
        return self._trial_manager.is_trial_active(tenant_id)

    def expire_trial(self, tenant_id: str) -> Dict[str, Any]:
        """Expire a trial and degrade to free."""
        return self._trial_manager.expire_trial(tenant_id)

    def extend_trial(self, tenant_id: str, additional_days: int) -> TrialInfo:
        """Extend a trial by additional days."""
        return self._trial_manager.extend_trial(tenant_id, additional_days)

    # ── Subscription lifecycle ─────────────────────────────

    def activate(
        self,
        tenant_id: str,
        payment_method_id: str = "",
        plan: PlanType = PlanType.BUSINESS,
    ) -> BillingRecord:
        """Activate a paid subscription.

        Args:
            tenant_id: Tenant identifier.
            payment_method_id: Stripe payment method ID.
            plan: Target plan.

        Returns:
            Updated BillingRecord.
        """
        return self._subscription_manager.activate_subscription(
            user_id=tenant_id,
            payment_method_id=payment_method_id,
            plan=plan,
        )

    def cancel(self, tenant_id: str, immediate: bool = False) -> bool:
        """Cancel a subscription.

        Args:
            tenant_id: Tenant identifier.
            immediate: Cancel immediately vs at period end.

        Returns:
            True if cancelled successfully.
        """
        try:
            self._subscription_manager.cancel_subscription(tenant_id, immediate=immediate)
            return True
        except ValueError:
            return False

    def change_plan(self, tenant_id: str, new_plan: PlanType) -> BillingRecord:
        """Change subscription plan."""
        return self._subscription_manager.change_plan(tenant_id, new_plan)

    # ── Status and access ──────────────────────────────────

    def get_status(self, tenant_id: str) -> Optional[BillingRecord]:
        """Get billing record for a tenant."""
        return self._subscription_manager.get_status(tenant_id)

    def get_plan(self, tenant_id: str) -> Dict[str, Any]:
        """Get current plan info for a tenant.

        Returns a dict suitable for the HTMX billing routes.
        """
        record = self.get_status(tenant_id)
        if record is None:
            return {
                "current": "free",
                "active": False,
                "is_trial": False,
                "days_remaining": None,
                "system_mode": "NORMAL",
                "features": [],
            }

        plan_name = record.plan_type.value if isinstance(record.plan_type, BillingPlan) else record.plan_type
        is_trial = record.status == SubscriptionStatus.TRIAL
        days_remaining = self._trial_manager.days_remaining(tenant_id) if is_trial else None

        # Check for degraded mode
        system_mode = "NORMAL"
        try:
            from src.core.degraded_mode import get_degraded_mode_manager
            dm = get_degraded_mode_manager()
            if dm and not dm.get_current_mode().is_normal:
                system_mode = dm.get_current_mode().value.upper()
        except Exception:
            pass

        # Features
        limits = PLAN_LIMITS.get(plan_name, PLAN_LIMITS["free"])
        features = [k for k, v in limits.items() if v is True]

        return {
            "current": plan_name,
            "active": SubscriptionStatus.is_active_status(record.status),
            "is_trial": is_trial,
            "days_remaining": days_remaining,
            "system_mode": system_mode,
            "features": features,
            "status": record.status.value if isinstance(record.status, SubscriptionStatus) else record.status,
        }

    def get_plans_catalog(self) -> List[Dict[str, Any]]:
        """Get available plans as a catalog list."""
        catalog = []
        for plan_key, limits in PLAN_LIMITS.items():
            plan_enum = BillingPlan(plan_key)
            catalog.append({
                "id": plan_key,
                "name": plan_enum.display_name,
                "price": plan_enum.monthly_price,
                "price_display": f"${plan_enum.monthly_price // 100}/mo" if plan_enum.monthly_price > 0 else "Free",
                "features": [k for k, v in limits.items() if v is True],
                "limits": limits,
            })
        return catalog

    def check_access(self, tenant_id: str, feature: str) -> tuple:
        """Check if tenant has access to a feature."""
        return self._subscription_manager.check_access(tenant_id, feature)

    # ── Usage ──────────────────────────────────────────────

    def get_usage(self, tenant_id: str, hours: int = 24) -> Dict[str, int]:
        """Get usage stats for the past N hours.

        Returns a dict of {event_type: count} for the HTMX usage endpoint.
        """
        usage_records = self._subscription_manager.get_usage(tenant_id)
        result: Dict[str, int] = {}
        for u in usage_records:
            result[u.feature_name] = u.usage_count
        return result

    def record_usage(self, tenant_id: str, feature: str, increment: int = 1) -> UsageRecord:
        """Record feature usage."""
        return self._subscription_manager.record_usage(tenant_id, feature, increment)

    # ── Stripe integration ─────────────────────────────────

    def create_checkout_session(
        self,
        tenant_id: str,
        plan_id: str,
    ) -> Dict[str, Any]:
        """Create a Stripe Checkout session.

        Args:
            tenant_id: Tenant identifier.
            plan_id: Plan ID (e.g. 'starter', 'business').

        Returns:
            Dict with 'checkout_url' or 'error'.
        """
        if not self._stripe_integration:
            return {"checkout_url": "", "error": "Stripe not configured"}

        record = self.get_status(tenant_id)
        if record is None:
            return {"checkout_url": "", "error": "No billing record found"}

        if not record.stripe_customer_id:
            return {"checkout_url": "", "error": "No Stripe customer ID. Start a trial first."}

        # Map plan_id to Stripe price ID
        price_map = {
            "starter": os.environ.get("STRIPE_STARTER_PRICE_ID", ""),
            "business": os.environ.get("STRIPE_BUSINESS_PRICE_ID", ""),
            "enterprise": os.environ.get("STRIPE_ENTERPRISE_PRICE_ID", ""),
        }
        price_id = price_map.get(plan_id, "")
        if not price_id:
            return {"checkout_url": "", "error": f"No Stripe price configured for plan '{plan_id}'"}

        try:
            import asyncio

            base_url = os.environ.get("BASE_URL", "http://localhost:8000")

            async def _create():
                return await self._stripe_integration.create_checkout_session(
                    customer=record.stripe_customer_id,
                    line_items=[{"price": price_id, "quantity": 1}],
                    success_url=f"{base_url}/htmx/billing?session_id={{CHECKOUT_SESSION_ID}}",
                    cancel_url=f"{base_url}/htmx/billing",
                )

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        session = loop.run_in_executor(pool, lambda: asyncio.run(_create()))
                else:
                    session = loop.run_until_complete(_create())
            except RuntimeError:
                session = asyncio.run(_create())

            return {"checkout_url": session.get("url", ""), "session_id": session.get("id", "")}

        except Exception as exc:
            logger.error("BillingService: create_checkout_session error: %s", exc)
            return {"checkout_url": "", "error": str(exc)}

    def create_portal_session(self, tenant_id: str, return_url: str = "") -> Dict[str, Any]:
        """Create a Stripe Customer Portal session."""
        if not self._stripe_integration:
            return {"url": "", "error": "Stripe not configured"}

        record = self.get_status(tenant_id)
        if record is None or not record.stripe_customer_id:
            return {"url": "", "error": "No Stripe customer ID"}

        try:
            import asyncio

            if not return_url:
                base_url = os.environ.get("BASE_URL", "http://localhost:8000")
                return_url = f"{base_url}/htmx/billing"

            async def _create():
                return await self._stripe_integration.create_portal_session(
                    customer=record.stripe_customer_id,
                    return_url=return_url,
                )

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        session = loop.run_in_executor(pool, lambda: asyncio.run(_create()))
                else:
                    session = loop.run_until_complete(_create())
            except RuntimeError:
                session = asyncio.run(_create())

            return {"url": session.get("url", "")}

        except Exception as exc:
            logger.error("BillingService: create_portal_session error: %s", exc)
            return {"url": "", "error": str(exc)}

    # ── Webhook processing ─────────────────────────────────

    def handle_webhook(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a parsed webhook event."""
        return self._subscription_manager.process_webhook_event(event)

    def process_webhook(self, payload: str, sig_header: str) -> bool:
        """Process a raw webhook payload.

        Args:
            payload: Raw JSON string.
            sig_header: Stripe-Signature header.

        Returns:
            True if processed successfully.
        """
        try:
            if self._stripe_client:
                event = self._stripe_client.verify_webhook_signature(
                    payload.encode("utf-8"), sig_header,
                )
                if not event:
                    return False

            event_data = json.loads(payload) if isinstance(payload, str) else payload
            result = self._subscription_manager.process_webhook_event(event_data)
            return result.get("status") in ("ok", "acknowledged")
        except Exception as exc:
            logger.error("BillingService: process_webhook error: %s", exc)
            return False

    # ── Invoices ───────────────────────────────────────────

    def get_invoices(self, tenant_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get invoice history for a tenant."""
        return self._subscription_manager.get_invoices(tenant_id, limit)


# ── Singleton management ──────────────────────────────────

_billing_service: Optional[BillingService] = None
_billing_lock = threading.Lock()


def get_billing_service() -> BillingService:
    """Get or create the singleton BillingService instance."""
    global _billing_service
    if _billing_service is None:
        with _billing_lock:
            if _billing_service is None:
                import os
                from pathlib import Path
                db_dir = Path.home() / ".zenic_agents" / "db"
                db_dir.mkdir(parents=True, exist_ok=True)
                db_path = str(db_dir / "billing.sqlite")
                _billing_service = BillingService(db_path=db_path)
    return _billing_service


def reset_billing_service() -> None:
    """Reset the singleton (for testing)."""
    global _billing_service
    with _billing_lock:
        _billing_service = None
