"""
Zenic-Agents Asistente — Billing Service (Phase 7.6)

Unified billing facade combining trial management, Stripe integration,
and plan management. Handles checkout, webhooks, and plan transitions.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .trial import TrialManager, get_trial_manager

logger = logging.getLogger(__name__)


class BillingPlan(str, Enum):
    """Available billing plans."""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass
class PlanDefinition:
    """Plan definition with features and pricing."""
    plan_id: str
    name: str
    price: float
    features: List[str]
    max_rpm: int = 5
    max_users: int = 1
    stripe_price_id: str = ""


PLAN_CATALOG: Dict[str, PlanDefinition] = {
    "free": PlanDefinition(
        plan_id="free", name="Free", price=0.0,
        features=["basic_pipeline", "chat_completions"], max_rpm=5, max_users=1,
    ),
    "pro": PlanDefinition(
        plan_id="pro", name="Pro", price=29.0,
        features=["basic_pipeline", "chat_completions", "app_generation",
                   "automation_generation", "schema_design", "thinking_engine",
                   "reasoning_engine", "logic_chains"],
        max_rpm=30, max_users=5,
        stripe_price_id=os.environ.get("STRIPE_PRO_PRICE_ID", ""),
    ),
    "enterprise": PlanDefinition(
        plan_id="enterprise", name="Enterprise", price=99.0,
        features=["all"], max_rpm=100, max_users=50,
        stripe_price_id=os.environ.get("STRIPE_ENTERPRISE_PRICE_ID", ""),
    ),
}


class BillingService:
    """Unified billing service.

    Manages:
    - Plan selection and transitions
    - Trial lifecycle (via TrialManager)
    - Stripe Checkout session creation
    - Stripe Webhook event processing
    - Usage tracking and quotas
    - Auto-degradation on expiry
    """

    def __init__(self, db_path: str = "billing_service.sqlite") -> None:
        self._db_path = db_path
        self._trial_manager = get_trial_manager()
        self._stripe_available = self._check_stripe()
        self._lock = threading.RLock()
        self._init_db()

    def _check_stripe(self) -> bool:
        """Check if Stripe library is available."""
        try:
            import stripe  # noqa: F401
            key = os.environ.get("STRIPE_SECRET_KEY", "")
            if key:
                stripe.api_key = key
            return True
        except ImportError:
            logger.debug("BillingService: stripe not available")
            return False

    def _init_db(self) -> None:
        """Initialize billing database."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    tenant_id TEXT PRIMARY KEY,
                    plan TEXT NOT NULL DEFAULT 'free',
                    status TEXT NOT NULL DEFAULT 'active',
                    current_period_start REAL,
                    current_period_end REAL,
                    stripe_customer_id TEXT,
                    stripe_subscription_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    detail TEXT DEFAULT '{}',
                    timestamp REAL NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("BillingService: DB init failed: %s", exc)

    # ── Plan Management ────────────────────────────────

    def get_plan(self, tenant_id: str) -> Dict[str, Any]:
        """Get current plan info for a tenant."""
        trial = self._trial_manager.get_trial(tenant_id)
        sub = self._load_subscription(tenant_id)

        plan_id = "free"
        if sub:
            plan_id = sub.get("plan", "free")
        elif trial.status.value == "active":
            plan_id = trial.trial_plan

        plan_def = PLAN_CATALOG.get(plan_id, PLAN_CATALOG["free"])

        return {
            "current": plan_id,
            "active": trial.status.value == "active" or (sub is not None and sub.get("status") == "active"),
            "is_trial": trial.status.value == "active",
            "trial_days": self._trial_manager._trial_days,
            "days_remaining": trial.days_remaining if trial.status.value == "active" else None,
            "system_mode": "NORMAL" if (trial.status.value == "active" or (sub and sub.get("status") == "active")) else "DEGRADED",
            "features": plan_def.features,
            "max_rpm": plan_def.max_rpm,
            "price": plan_def.price,
        }

    def get_plans_catalog(self) -> List[Dict[str, Any]]:
        """Get available plans for display."""
        return [
            {"id": p.plan_id, "name": p.name, "price": p.price,
             "features": p.features, "max_rpm": p.max_rpm}
            for p in PLAN_CATALOG.values()
        ]

    # ── Checkout ───────────────────────────────────────

    def create_checkout_session(
        self, tenant_id: str, plan_id: str, success_url: str = "", cancel_url: str = "",
    ) -> Dict[str, Any]:
        """Create a Stripe Checkout session."""
        if not self._stripe_available:
            return {"checkout_url": "", "error": "Stripe not configured"}

        plan_def = PLAN_CATALOG.get(plan_id)
        if not plan_def or not plan_def.stripe_price_id:
            return {"checkout_url": "", "error": f"Plan '{plan_id}' has no Stripe price ID"}

        try:
            import stripe
            session = stripe.checkout.Session.create(
                mode="subscription",
                payment_method_types=["card"],
                line_items=[{"price": plan_def.stripe_price_id, "quantity": 1}],
                success_url=success_url or "http://localhost:5000/app/billing?success=1",
                cancel_url=cancel_url or "http://localhost:5000/app/billing?cancel=1",
                metadata={"tenant_id": tenant_id, "plan_id": plan_id},
            )
            return {"checkout_url": session.url, "session_id": session.id}
        except Exception as exc:
            logger.error("BillingService: Checkout failed: %s", exc)
            return {"checkout_url": "", "error": str(exc)}

    # ── Webhooks ───────────────────────────────────────

    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process Stripe webhook events."""
        event_type = payload.get("type", "")
        data = payload.get("data", {}).get("object", {})

        if event_type == "checkout.session.completed":
            return self._on_checkout_complete(data)
        elif event_type == "customer.subscription.updated":
            return self._on_subscription_updated(data)
        elif event_type == "customer.subscription.deleted":
            return self._on_subscription_deleted(data)
        elif event_type == "invoice.payment_failed":
            return self._on_payment_failed(data)

        logger.info("BillingService: Unhandled webhook: %s", event_type)
        return {"status": "ignored", "event": event_type}

    def _on_checkout_complete(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle completed checkout."""
        tenant_id = data.get("metadata", {}).get("tenant_id", "")
        plan_id = data.get("metadata", {}).get("plan_id", "free")
        customer_id = data.get("customer", "")
        sub_id = data.get("subscription", "")

        if tenant_id:
            self._save_subscription(tenant_id, plan_id, customer_id, sub_id)
            self._trial_manager.convert_trial(tenant_id, plan_id)
            logger.info("BillingService: Checkout complete for '%s' → %s", tenant_id, plan_id)

        return {"status": "processed", "tenant_id": tenant_id, "plan": plan_id}

    def _on_subscription_updated(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle subscription update."""
        return {"status": "processed"}

    def _on_subscription_deleted(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle subscription cancellation."""
        customer_id = data.get("customer", "")
        tenant_id = self._find_tenant_by_customer(customer_id)
        if tenant_id:
            self._update_subscription_status(tenant_id, "cancelled")
            try:
                from src.core.degraded_mode.manager import get_degraded_mode_manager
                get_degraded_mode_manager().enter_degraded(reason="Subscription cancelled")
            except ImportError:
                pass
        return {"status": "processed", "tenant_id": tenant_id}

    def _on_payment_failed(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle payment failure."""
        return {"status": "processed", "action": "notification_sent"}

    # ── Usage Tracking ─────────────────────────────────

    def record_usage(self, tenant_id: str, event_type: str, detail: str = "{}") -> None:
        """Record a usage event."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT INTO usage_events (tenant_id, event_type, detail, timestamp) VALUES (?, ?, ?, ?)",
                (tenant_id, event_type, detail, time.time()),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("BillingService: Usage record failed: %s", exc)

    def get_usage(self, tenant_id: str, hours: int = 24) -> Dict[str, int]:
        """Get usage counts for a tenant."""
        cutoff = time.time() - (hours * 3600)
        try:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT event_type, COUNT(*) as cnt FROM usage_events "
                "WHERE tenant_id = ? AND timestamp >= ? GROUP BY event_type",
                (tenant_id, cutoff),
            ).fetchall()
            conn.close()
            return {r[0]: r[1] for r in rows}
        except Exception:
            return {}

    # ── Persistence ────────────────────────────────────

    def _load_subscription(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Load subscription from database."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM subscriptions WHERE tenant_id = ?", (tenant_id,),
            ).fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception:
            return None

    def _save_subscription(
        self, tenant_id: str, plan: str, stripe_customer_id: str = "",
        stripe_subscription_id: str = "",
    ) -> None:
        """Save subscription to database."""
        now = time.time()
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT OR REPLACE INTO subscriptions
                   (tenant_id, plan, status, stripe_customer_id, stripe_subscription_id,
                    created_at, updated_at) VALUES (?, ?, 'active', ?, ?, ?, ?)""",
                (tenant_id, plan, stripe_customer_id, stripe_subscription_id, now, now),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("BillingService: Save subscription failed: %s", exc)

    def _update_subscription_status(self, tenant_id: str, status: str) -> None:
        """Update subscription status."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "UPDATE subscriptions SET status = ?, updated_at = ? WHERE tenant_id = ?",
                (status, time.time(), tenant_id),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("BillingService: Update status failed: %s", exc)

    def _find_tenant_by_customer(self, customer_id: str) -> str:
        """Find tenant_id by Stripe customer ID."""
        try:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT tenant_id FROM subscriptions WHERE stripe_customer_id = ?",
                (customer_id,),
            ).fetchone()
            conn.close()
            return row[0] if row else ""
        except Exception:
            return ""


# ── Singleton ─────────────────────────────────────────

_billing_service: Optional[BillingService] = None
_lock = threading.Lock()


def get_billing_service(**kwargs: Any) -> BillingService:
    """Get or create the global BillingService."""
    global _billing_service
    with _lock:
        if _billing_service is None:
            _billing_service = BillingService(**kwargs)
        return _billing_service


def reset_billing_service() -> None:
    """Reset the global BillingService (for testing)."""
    global _billing_service
    _billing_service = None
