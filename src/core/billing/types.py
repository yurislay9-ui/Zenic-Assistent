"""
Billing type definitions — dataclasses, enums, and constants.

Defines the core data model for the billing subsystem:
- BillingPlan / PlanType: pricing tiers
- SubscriptionStatus: subscription lifecycle states
- InvoiceStatus: payment invoice states
- BillingRecord: persisted subscription record (mutable, per-tenant)
- BillingEvent: event log entry for billing actions
- UsageRecord: feature usage tracking record
- TrialInfo: trial period metadata
- Subscription: subscription details ( Stripe-linked )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Constants ──────────────────────────────────────────────

TRIAL_DURATION_DAYS: int = 14
"""Default trial length in days."""

# ── Stripe price ID mapping (env vars override) ──────────

import os as _os

STRIPE_PRICE_IDS: Dict[str, str] = {
    "starter": _os.environ.get("STRIPE_STARTER_PRICE_ID", ""),
    "business": _os.environ.get("STRIPE_BUSINESS_PRICE_ID", ""),
    "enterprise": _os.environ.get("STRIPE_ENTERPRISE_PRICE_ID", ""),
}
"""Stripe price IDs per plan — set via environment variables."""


# ── Enums ──────────────────────────────────────────────────

class BillingPlan(str, Enum):
    """Billing plan tiers — maps to Stripe price IDs in production."""
    FREE = "free"
    STARTER = "starter"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"

    @property
    def display_name(self) -> str:
        names = {
            "free": "Free",
            "starter": "Starter",
            "business": "Business",
            "enterprise": "Enterprise",
        }
        return names.get(self.value, self.value)

    @property
    def monthly_price(self) -> int:
        """Price in cents per month (0 for free / enterprise custom)."""
        prices = {"free": 0, "starter": 2900, "business": 7900, "enterprise": 0}
        return prices.get(self.value, 0)


# Backward-compatible alias used by E2E tests
PlanType = BillingPlan


class SubscriptionStatus(str, Enum):
    """Subscription lifecycle states."""
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    CANCELED = "canceled"      # US-spelling alias
    EXPIRED = "expired"
    DEGRADED = "degraded"      # trial expired → free-tier degraded

    @classmethod
    def is_active_status(cls, status: "SubscriptionStatus") -> bool:
        return status in (cls.TRIAL, cls.ACTIVE)


class InvoiceStatus(str, Enum):
    """Payment invoice states."""
    DRAFT = "draft"
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


# ── Plan Limits ────────────────────────────────────────────

PLAN_LIMITS: Dict[str, Dict[str, Any]] = {
    "free": {
        "actions_per_day": 100,
        "monitors": 5,
        "users": 1,
        "api_access": False,
        "webhooks": False,
        "sso": False,
        "priority_support": False,
    },
    "starter": {
        "actions_per_day": 1_000,
        "monitors": 10,
        "users": 3,
        "api_access": True,
        "webhooks": False,
        "sso": False,
        "priority_support": False,
    },
    "business": {
        "actions_per_day": -1,   # unlimited
        "monitors": -1,          # unlimited
        "users": 10,
        "api_access": True,
        "webhooks": True,
        "sso": False,
        "priority_support": False,
    },
    "enterprise": {
        "actions_per_day": -1,
        "monitors": -1,
        "users": -1,
        "api_access": True,
        "webhooks": True,
        "sso": True,
        "priority_support": True,
    },
}


# ── Data classes ───────────────────────────────────────────

@dataclass
class BillingEvent:
    """Immutable log entry for a billing action."""
    event_type: str
    timestamp: float
    plan: str
    amount: int = 0           # cents
    currency: str = "usd"
    user_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "plan": self.plan,
            "amount": self.amount,
            "currency": self.currency,
            "user_id": self.user_id,
            "metadata": self.metadata,
        }


@dataclass
class UsageRecord:
    """Feature usage tracking — current usage vs plan limit."""
    feature_name: str
    usage_count: int
    limit: int                # -1 = unlimited
    period_start: float
    period_end: float

    @property
    def is_unlimited(self) -> bool:
        return self.limit < 0

    @property
    def is_over_limit(self) -> bool:
        if self.is_unlimited:
            return False
        return self.usage_count >= self.limit

    @property
    def remaining(self) -> int:
        if self.is_unlimited:
            return -1
        return max(0, self.limit - self.usage_count)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "usage_count": self.usage_count,
            "limit": self.limit,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "is_unlimited": self.is_unlimited,
            "is_over_limit": self.is_over_limit,
            "remaining": self.remaining,
        }


@dataclass
class TrialInfo:
    """Trial period metadata."""
    started_at: float
    expires_at: float
    plan_during_trial: str = "business"

    @property
    def days_remaining(self) -> int:
        import time as _time
        remaining = (self.expires_at - _time.time()) / 86400
        return max(0, int(remaining))

    @property
    def is_expired(self) -> bool:
        import time as _time
        return _time.time() >= self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at,
            "expires_at": self.expires_at,
            "days_remaining": self.days_remaining,
            "is_expired": self.is_expired,
            "plan_during_trial": self.plan_during_trial,
        }


@dataclass
class Subscription:
    """Subscription details — linked to Stripe when available."""
    user_id: str
    plan: str
    status: str
    stripe_customer_id: str = ""
    stripe_subscription_id: str = ""
    current_period_start: float = 0.0
    current_period_end: float = 0.0
    cancel_at_period_end: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "plan": self.plan,
            "status": self.status,
            "stripe_customer_id": self.stripe_customer_id,
            "stripe_subscription_id": self.stripe_subscription_id,
            "current_period_start": self.current_period_start,
            "current_period_end": self.current_period_end,
            "cancel_at_period_end": self.cancel_at_period_end,
        }


@dataclass
class InvoiceRecord:
    """Stripe invoice record (used by StripeIntegration.list_invoices)."""
    tenant_id: str = ""
    invoice_id: str = ""
    amount_cents: int = 0
    status: str = "draft"
    created_at: float = 0.0
    pdf_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "invoice_id": self.invoice_id,
            "amount_cents": self.amount_cents,
            "status": self.status,
            "created_at": self.created_at,
            "pdf_url": self.pdf_url,
        }


@dataclass
class BillingRecord:
    """Mutable per-tenant billing record persisted in SQLite.

    This is the primary data model used by TrialManager, SubscriptionManager,
    and BillingService.  It stores the complete lifecycle state of a tenant's
    billing: trial start/end, current plan, status, Stripe IDs, etc.
    """
    tenant_id: str
    status: SubscriptionStatus = SubscriptionStatus.TRIAL
    plan_type: BillingPlan = BillingPlan.BUSINESS
    trial_start: float = 0.0
    trial_end: float = 0.0
    stripe_customer_id: str = ""
    stripe_subscription_id: str = ""
    current_period_start: float = 0.0
    current_period_end: float = 0.0
    cancel_at_period_end: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "status": self.status.value if isinstance(self.status, SubscriptionStatus) else self.status,
            "plan_type": self.plan_type.value if isinstance(self.plan_type, BillingPlan) else self.plan_type,
            "trial_start": self.trial_start,
            "trial_end": self.trial_end,
            "stripe_customer_id": self.stripe_customer_id,
            "stripe_subscription_id": self.stripe_subscription_id,
            "current_period_start": self.current_period_start,
            "current_period_end": self.current_period_end,
            "cancel_at_period_end": self.cancel_at_period_end,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "BillingRecord":
        """Build from a SQLite row dict."""
        status_val = row.get("status", "trial")
        plan_val = row.get("plan_type", "business")
        # Normalize to enum members
        try:
            status_enum = SubscriptionStatus(status_val)
        except ValueError:
            status_enum = SubscriptionStatus.TRIAL
        try:
            plan_enum = BillingPlan(plan_val)
        except ValueError:
            plan_enum = BillingPlan.BUSINESS

        return cls(
            tenant_id=row.get("tenant_id", ""),
            status=status_enum,
            plan_type=plan_enum,
            trial_start=row.get("trial_start", 0.0),
            trial_end=row.get("trial_end", 0.0),
            stripe_customer_id=row.get("stripe_customer_id", ""),
            stripe_subscription_id=row.get("stripe_subscription_id", ""),
            current_period_start=row.get("current_period_start", 0.0),
            current_period_end=row.get("current_period_end", 0.0),
            cancel_at_period_end=bool(row.get("cancel_at_period_end", 0)),
            created_at=row.get("created_at", 0.0),
            updated_at=row.get("updated_at", 0.0),
        )
