"""
BillingWebhookHandler — Stripe webhook endpoint handler.

Verifies Stripe webhook signatures, parses events, and delegates
to the SubscriptionManager for processing.

Also provides a ``WebhookHandler`` alias for backward compatibility
with existing E2E tests.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

from .stripe_client import StripeClient, StripeAPIError
from .subscription_manager import SubscriptionManager

logger = logging.getLogger(__name__)


class BillingWebhookHandler:
    """Stripe webhook endpoint handler.

    Verifies signatures, parses events, and routes to the
    appropriate handler method based on event type.

    Args:
        subscription_manager: The SubscriptionManager for processing events.
        stripe_client: Optional StripeClient for signature verification.
    """

    def __init__(
        self,
        subscription_manager: SubscriptionManager,
        stripe_client: Optional[StripeClient] = None,
    ) -> None:
        self._sub_manager = subscription_manager
        self._stripe_client = stripe_client

    # ── Main entry point ───────────────────────────────────

    def handle_stripe_webhook(
        self,
        request_body: bytes,
        sig_header: str,
    ) -> Dict[str, Any]:
        """Main entry point for Stripe webhook handling.

        1. Verifies the Stripe signature
        2. Parses the event payload
        3. Routes to the appropriate handler

        Args:
            request_body: Raw request body bytes.
            sig_header: Stripe-Signature header value.

        Returns:
            Dict with 'status' and 'message'.
        """
        # Verify signature
        if self._stripe_client:
            try:
                if not self._stripe_client.verify_webhook_signature(request_body, sig_header):
                    return {"status": "error", "message": "Invalid signature", "http_code": 400}
            except Exception as exc:
                logger.error("BillingWebhookHandler: signature verification error: %s", exc)
                return {"status": "error", "message": "Signature verification failed", "http_code": 400}

        # Parse event
        try:
            event = json.loads(request_body)
        except json.JSONDecodeError as exc:
            logger.error("BillingWebhookHandler: JSON parse error: %s", exc)
            return {"status": "error", "message": "Invalid JSON payload", "http_code": 400}

        # Route to handler
        event_type = event.get("type", "")
        logger.info("BillingWebhookHandler: processing event '%s'", event_type)

        handlers = {
            "checkout.session.completed": self._handle_checkout_completed,
            "customer.subscription.updated": self._handle_subscription_updated,
            "customer.subscription.deleted": self._handle_subscription_deleted,
            "invoice.payment_failed": self._handle_payment_failed,
            "invoice.paid": self._handle_invoice_paid,
            "invoice.payment_action_required": self._handle_invoice_payment_action_required,
        }

        handler = handlers.get(event_type)
        if handler:
            try:
                result = handler(event)
                return result
            except Exception as exc:
                logger.error("BillingWebhookHandler: handler error for '%s': %s", event_type, exc)
                return {"status": "error", "message": str(exc), "http_code": 500}

        # Unhandled events are acknowledged (Stripe expects 200)
        return {"status": "acknowledged", "message": f"Unhandled event: {event_type}", "http_code": 200}

    # ── Event handlers ─────────────────────────────────────

    def _handle_checkout_completed(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Activate subscription after successful checkout."""
        return self._sub_manager.process_webhook_event(event)

    def _handle_subscription_updated(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Update local subscription record."""
        return self._sub_manager.process_webhook_event(event)

    def _handle_subscription_deleted(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle subscription cancellation."""
        return self._sub_manager.process_webhook_event(event)

    def _handle_payment_failed(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Send dunning email and mark subscription as past_due."""
        result = self._sub_manager.process_webhook_event(event)

        # Send dunning notification
        data = event.get("data", {}).get("object", {})
        customer_id = data.get("customer", "")
        attempt_count = data.get("attempt_count", 1)

        try:
            from src.core.executors.notification_executor import NotificationExecutor
            import asyncio

            notifier = NotificationExecutor()

            async def _send_dunning():
                await notifier.execute({
                    "channel": "log",
                    "message": (
                        f"Payment failed for customer {customer_id} "
                        f"(attempt {attempt_count}). Please update your payment method."
                    ),
                    "subject": "Payment Failed — Action Required",
                    "recipient": customer_id,
                }, {})

            try:
                asyncio.run(_send_dunning())
            except RuntimeError:
                pass
        except Exception as exc:
            logger.warning("BillingWebhookHandler: dunning notification failed: %s", exc)

        return result

    def _handle_invoice_paid(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Record successful payment."""
        return self._sub_manager.process_webhook_event(event)

    def _handle_invoice_payment_action_required(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle SCA (Strong Customer Authentication) requirement.

        The customer needs to complete authentication for the payment
        to proceed. We log this and send a notification.
        """
        data = event.get("data", {}).get("object", {})
        customer_id = data.get("customer", "")
        payment_intent_id = data.get("payment_intent", "")

        logger.warning(
            "BillingWebhookHandler: SCA required for customer %s, payment_intent=%s",
            customer_id, payment_intent_id,
        )

        try:
            from src.core.executors.notification_executor import NotificationExecutor
            import asyncio

            notifier = NotificationExecutor()

            async def _send_sca():
                await notifier.execute({
                    "channel": "log",
                    "message": (
                        f"Additional authentication required for payment. "
                        f"Customer: {customer_id}, Payment Intent: {payment_intent_id}"
                    ),
                    "subject": "Payment Authentication Required",
                    "recipient": customer_id,
                }, {})

            try:
                asyncio.run(_send_sca())
            except RuntimeError:
                pass
        except Exception as exc:
            logger.warning("BillingWebhookHandler: SCA notification failed: %s", exc)

        return {"status": "ok", "message": "SCA action required notification sent"}


# ── Backward-compatible alias ─────────────────────────────
# E2E tests import WebhookHandler from this module

class WebhookHandler(BillingWebhookHandler):
    """Backward-compatible alias for BillingWebhookHandler.

    The E2E tests create WebhookHandler(stripe_integration=..., trial_manager=...).
    This subclass accepts the old constructor signature and adapts it.
    """

    def __init__(
        self,
        stripe_integration: Optional[Any] = None,
        trial_manager: Optional[Any] = None,
        subscription_manager: Optional[SubscriptionManager] = None,
    ) -> None:
        # Build SubscriptionManager from trial_manager if needed
        if subscription_manager is not None:
            sub_mgr = subscription_manager
        elif trial_manager is not None:
            # Reuse the same DB path from the trial manager
            sub_mgr = SubscriptionManager(
                db_path=getattr(trial_manager, "_db_path", "billing.db"),
            )
        else:
            sub_mgr = SubscriptionManager()

        # Build StripeClient from stripe_integration if needed
        stripe_client = None
        if stripe_integration is not None:
            stripe_client = getattr(stripe_integration, "_client", None)

        super().__init__(
            subscription_manager=sub_mgr,
            stripe_client=stripe_client,
        )

        # Keep references for direct access in tests
        self._trial_manager = trial_manager
        self._stripe_integration = stripe_integration

    def handle_event(self, event: Dict[str, Any]) -> bool:
        """Handle a webhook event (simplified interface for E2E tests).

        Args:
            event: Parsed event dict with 'type' and 'data'.

        Returns:
            True if handled successfully, False otherwise.
        """
        try:
            result = self._sub_manager.process_webhook_event(event)
            return result.get("status") in ("ok", "acknowledged")
        except Exception as exc:
            logger.error("WebhookHandler: handle_event error: %s", exc)
            return False
