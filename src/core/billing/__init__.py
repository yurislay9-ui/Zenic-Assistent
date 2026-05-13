"""
Zenic-Agents Billing Module — Stripe integration and trial management.

Provides the complete billing subsystem for SaaS monetization:

  - **Types**: BillingPlan, SubscriptionStatus, InvoiceStatus, BillingEvent,
    UsageRecord, TrialInfo, Subscription, BillingRecord
  - **StripeClient**: Real HTTP integration with Stripe API (aiohttp)
  - **StripeIntegration**: Facade for backward compatibility with E2E tests
  - **SubscriptionManager**: Subscription lifecycle, usage, access control
  - **TrialManager**: Trial-specific logic (start, expire, extend, remind)
  - **BillingWebhookHandler / WebhookHandler**: Stripe webhook processing
  - **BillingService**: Unified facade (singleton via get_billing_service)

Usage:
    from src.core.billing import get_billing_service

    svc = get_billing_service()
    record = svc.start_trial("tenant-123")
    plan_info = svc.get_plan("tenant-123")
    usage = svc.get_usage("tenant-123")
"""

# ── Types ─────────────────────────────────────────────────
from .types import (
    BillingPlan,
    BillingEvent,
    BillingRecord,
    InvoiceRecord,
    InvoiceStatus,
    PlanType,
    STRIPE_PRICE_IDS,
    Subscription,
    SubscriptionStatus,
    TrialInfo,
    UsageRecord,
    PLAN_LIMITS,
    TRIAL_DURATION_DAYS,
)

# ── Stripe client ─────────────────────────────────────────
from .stripe_client import (
    StripeClient,
    StripeAPIError,
    StripeRateLimitError,
)

# ── Stripe integration (SDK-based, backward compat) ────────
from .stripe_integration import StripeIntegration

# ── Subscription management ───────────────────────────────
from .subscription_manager import SubscriptionManager

# ── Trial management ──────────────────────────────────────
from .trial_manager import TrialManager

# ── Webhook handling ──────────────────────────────────────
from .webhook_handler import BillingWebhookHandler, WebhookHandler

# ── Service facade ────────────────────────────────────────
from .service import BillingService, get_billing_service, reset_billing_service


__all__ = [
    # Types
    "BillingPlan",
    "PlanType",
    "SubscriptionStatus",
    "InvoiceStatus",
    "BillingEvent",
    "BillingRecord",
    "InvoiceRecord",
    "UsageRecord",
    "TrialInfo",
    "Subscription",
    "PLAN_LIMITS",
    "TRIAL_DURATION_DAYS",
    # Stripe
    "StripeClient",
    "StripeIntegration",
    "STRIPE_PRICE_IDS",
    "StripeAPIError",
    "StripeRateLimitError",
    # Managers
    "SubscriptionManager",
    "TrialManager",
    # Handlers
    "BillingWebhookHandler",
    "WebhookHandler",
    # Service
    "BillingService",
    "get_billing_service",
    "reset_billing_service",
]
