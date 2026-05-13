"""
SubscriptionManager — subscription lifecycle management with SQLite persistence.

Handles the full subscription lifecycle:
  - Starting trials (14-day free trial with BUSINESS features)
  - Activating paid subscriptions
  - Canceling subscriptions (at period end or immediate)
  - Changing plans (upgrade/downgrade with proration)
  - Feature access checking
  - Usage recording and enforcement
  - Webhook event processing
  - Degraded access for expired trials

Works without Stripe in dev mode (SQLite-only subscriptions).
When StripeClient is provided, syncs changes to Stripe.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .types import (
    BillingEvent,
    BillingPlan,
    BillingRecord,
    PLAN_LIMITS,
    SubscriptionStatus,
    UsageRecord,
)
from .stripe_client import StripeClient

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """Subscription lifecycle manager with SQLite persistence.

    Args:
        stripe_client: Optional StripeClient for real Stripe API calls.
                       None = dev mode (SQLite only).
        db_path: Path to the SQLite database file.
    """

    def __init__(
        self,
        stripe_client: Optional[StripeClient] = None,
        db_path: str = "billing.db",
    ) -> None:
        self._stripe = stripe_client
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    # ── Database initialization ────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        """Get a SQLite connection with row factory."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        """Create billing tables if they don't exist."""
        conn = self._conn()
        try:
            conn.execute("""CREATE TABLE IF NOT EXISTS billing_records (
                tenant_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'trial',
                plan_type TEXT NOT NULL DEFAULT 'business',
                trial_start REAL DEFAULT 0,
                trial_end REAL DEFAULT 0,
                stripe_customer_id TEXT DEFAULT '',
                stripe_subscription_id TEXT DEFAULT '',
                current_period_start REAL DEFAULT 0,
                current_period_end REAL DEFAULT 0,
                cancel_at_period_end INTEGER DEFAULT 0,
                created_at REAL DEFAULT 0,
                updated_at REAL DEFAULT 0)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS usage_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                feature_name TEXT NOT NULL,
                usage_count INTEGER DEFAULT 0,
                period_start REAL NOT NULL,
                period_end REAL NOT NULL,
                UNIQUE(tenant_id, feature_name, period_start))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS billing_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                timestamp REAL NOT NULL,
                plan TEXT NOT NULL,
                amount INTEGER DEFAULT 0,
                currency TEXT DEFAULT 'usd',
                user_id TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}')""")
            # Indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_tenant ON usage_records(tenant_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON billing_events(event_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON billing_events(timestamp)")
            conn.commit()
            logger.info("SubscriptionManager: billing tables initialized at %s", self._db_path)
        except sqlite3.Error as e:
            logger.error("SubscriptionManager: _init_db error: %s", e)
        finally:
            conn.close()

    # ── Internal persistence helpers ───────────────────────

    def _save_record(self, record: BillingRecord) -> None:
        """Persist a BillingRecord to SQLite (upsert)."""
        conn = self._conn()
        try:
            with self._lock:
                conn.execute(
                    "INSERT INTO billing_records "
                    "(tenant_id, status, plan_type, trial_start, trial_end, "
                    "stripe_customer_id, stripe_subscription_id, "
                    "current_period_start, current_period_end, "
                    "cancel_at_period_end, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(tenant_id) DO UPDATE SET "
                    "status=excluded.status, plan_type=excluded.plan_type, "
                    "trial_start=excluded.trial_start, trial_end=excluded.trial_end, "
                    "stripe_customer_id=excluded.stripe_customer_id, "
                    "stripe_subscription_id=excluded.stripe_subscription_id, "
                    "current_period_start=excluded.current_period_start, "
                    "current_period_end=excluded.current_period_end, "
                    "cancel_at_period_end=excluded.cancel_at_period_end, "
                    "updated_at=excluded.updated_at",
                    (
                        record.tenant_id,
                        record.status.value if isinstance(record.status, SubscriptionStatus) else record.status,
                        record.plan_type.value if isinstance(record.plan_type, BillingPlan) else record.plan_type,
                        record.trial_start,
                        record.trial_end,
                        record.stripe_customer_id,
                        record.stripe_subscription_id,
                        record.current_period_start,
                        record.current_period_end,
                        int(record.cancel_at_period_end),
                        record.created_at,
                        record.updated_at,
                    ),
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error("SubscriptionManager: _save_record error: %s", e)
        finally:
            conn.close()

    def _get_record(self, tenant_id: str) -> Optional[BillingRecord]:
        """Load a BillingRecord from SQLite."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM billing_records WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            if row is None:
                return None
            return BillingRecord.from_row(dict(row))
        except sqlite3.Error as e:
            logger.error("SubscriptionManager: _get_record error: %s", e)
            return None
        finally:
            conn.close()

    def _log_event(self, event: BillingEvent) -> None:
        """Persist a billing event."""
        conn = self._conn()
        try:
            with self._lock:
                conn.execute(
                    "INSERT INTO billing_events (event_type, timestamp, plan, amount, currency, user_id, metadata) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.event_type,
                        event.timestamp,
                        event.plan,
                        event.amount,
                        event.currency,
                        event.user_id,
                        json.dumps(event.metadata),
                    ),
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error("SubscriptionManager: _log_event error: %s", e)
        finally:
            conn.close()

    # ── Trial management ───────────────────────────────────

    def start_trial(
        self,
        user_id: str,
        email: str,
        plan: BillingPlan = BillingPlan.BUSINESS,
    ) -> BillingRecord:
        """Start a 14-day trial for a new tenant.

        If a record already exists for this user_id, return the existing one
        (idempotent start).

        Args:
            user_id: Unique user/tenant identifier.
            email: User email (used for Stripe customer creation).
            plan: Plan to trial (default BUSINESS).

        Returns:
            The BillingRecord in TRIAL status.
        """
        # Idempotent: return existing if present
        existing = self._get_record(user_id)
        if existing is not None:
            logger.info("SubscriptionManager: start_trial idempotent return for %s", user_id)
            return existing

        now = time.time()
        trial_end = now + (14 * 86400)

        # Create Stripe customer if client available
        stripe_customer_id = ""
        if self._stripe and self._stripe._api_key:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're inside an async context; schedule it
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        cust = loop.run_in_executor(
                            pool,
                            lambda: asyncio.run(
                                self._stripe.create_customer(
                                    email=email,
                                    name=user_id,
                                    metadata={"tenant_id": user_id},
                                )
                            ),
                        )
                else:
                    cust = self._stripe.create_customer(
                        email=email,
                        name=user_id,
                        metadata={"tenant_id": user_id},
                    )
                stripe_customer_id = cust.get("id", "")
            except Exception as exc:
                logger.warning("SubscriptionManager: Stripe customer creation failed: %s", exc)

        record = BillingRecord(
            tenant_id=user_id,
            status=SubscriptionStatus.TRIAL,
            plan_type=plan,
            trial_start=now,
            trial_end=trial_end,
            stripe_customer_id=stripe_customer_id,
            created_at=now,
            updated_at=now,
        )
        self._save_record(record)

        self._log_event(BillingEvent(
            event_type="trial_started",
            timestamp=now,
            plan=plan.value,
            user_id=user_id,
            metadata={"trial_end": trial_end, "email": email},
        ))

        logger.info("SubscriptionManager: trial started for %s (plan=%s, expires=%s)",
                     user_id, plan.value, trial_end)
        return record

    # ── Subscription activation ────────────────────────────

    def activate_subscription(
        self,
        user_id: str,
        payment_method_id: str,
        plan: BillingPlan,
    ) -> BillingRecord:
        """Activate a paid subscription.

        Args:
            user_id: User/tenant identifier.
            payment_method_id: Stripe payment method ID (e.g. ``pm_...``).
            plan: Target billing plan.

        Returns:
            Updated BillingRecord in ACTIVE status.

        Raises:
            ValueError: If no record exists for this user.
        """
        record = self._get_record(user_id)
        if record is None:
            raise ValueError(f"No billing record found for user {user_id}")

        now = time.time()
        period_end = now + (30 * 86400)  # 30-day billing period

        # Create Stripe subscription if client available
        stripe_subscription_id = ""
        if self._stripe and self._stripe._api_key:
            try:
                # Map plan to Stripe price ID (env-configurable)
                import os
                price_map = {
                    "starter": os.environ.get("STRIPE_STARTER_PRICE_ID", ""),
                    "business": os.environ.get("STRIPE_BUSINESS_PRICE_ID", ""),
                    "enterprise": os.environ.get("STRIPE_ENTERPRISE_PRICE_ID", ""),
                }
                price_id = price_map.get(plan.value, "")
                if price_id and record.stripe_customer_id:
                    import asyncio
                    sub = asyncio.get_event_loop().run_until_complete(
                        self._stripe.create_subscription(
                            customer_id=record.stripe_customer_id,
                            price_id=price_id,
                            trial_days=0,
                        )
                    )
                    stripe_subscription_id = sub.get("id", "")
            except Exception as exc:
                logger.warning("SubscriptionManager: Stripe subscription creation failed: %s", exc)

        record.status = SubscriptionStatus.ACTIVE
        record.plan_type = plan
        record.current_period_start = now
        record.current_period_end = period_end
        record.stripe_subscription_id = stripe_subscription_id or record.stripe_subscription_id
        record.cancel_at_period_end = False
        record.updated_at = now

        self._save_record(record)

        self._log_event(BillingEvent(
            event_type="subscription_activated",
            timestamp=now,
            plan=plan.value,
            amount=plan.monthly_price,
            user_id=user_id,
            metadata={"payment_method_id": payment_method_id},
        ))

        logger.info("SubscriptionManager: subscription activated for %s (plan=%s)", user_id, plan.value)
        return record

    # ── Subscription cancellation ──────────────────────────

    def cancel_subscription(
        self,
        user_id: str,
        immediate: bool = False,
    ) -> BillingRecord:
        """Cancel a subscription.

        Args:
            user_id: User/tenant identifier.
            immediate: If True, cancel immediately. Otherwise cancel at period end.

        Returns:
            Updated BillingRecord.

        Raises:
            ValueError: If no record exists for this user.
        """
        record = self._get_record(user_id)
        if record is None:
            raise ValueError(f"No billing record found for user {user_id}")

        now = time.time()

        if immediate:
            # Cancel immediately in Stripe
            if self._stripe and record.stripe_subscription_id:
                try:
                    import asyncio
                    asyncio.get_event_loop().run_until_complete(
                        self._stripe.cancel_subscription(
                            record.stripe_subscription_id,
                            at_period_end=False,
                        )
                    )
                except Exception as exc:
                    logger.warning("SubscriptionManager: Stripe cancel failed: %s", exc)

            record.status = SubscriptionStatus.CANCELED
            record.plan_type = BillingPlan.FREE
            record.cancel_at_period_end = False
            record.updated_at = now
        else:
            # Cancel at period end
            if self._stripe and record.stripe_subscription_id:
                try:
                    import asyncio
                    asyncio.get_event_loop().run_until_complete(
                        self._stripe.cancel_subscription(
                            record.stripe_subscription_id,
                            at_period_end=True,
                        )
                    )
                except Exception as exc:
                    logger.warning("SubscriptionManager: Stripe cancel_at_period_end failed: %s", exc)

            record.cancel_at_period_end = True
            record.updated_at = now

        self._save_record(record)

        self._log_event(BillingEvent(
            event_type="subscription_cancelled",
            timestamp=now,
            plan=record.plan_type.value if isinstance(record.plan_type, BillingPlan) else record.plan_type,
            user_id=user_id,
            metadata={"immediate": immediate},
        ))

        logger.info("SubscriptionManager: subscription cancelled for %s (immediate=%s)", user_id, immediate)
        return record

    # ── Plan changes ───────────────────────────────────────

    def change_plan(self, user_id: str, new_plan: BillingPlan) -> BillingRecord:
        """Change the subscription plan (upgrade or downgrade with proration).

        Args:
            user_id: User/tenant identifier.
            new_plan: Target billing plan.

        Returns:
            Updated BillingRecord.

        Raises:
            ValueError: If no record exists or record is not ACTIVE.
        """
        record = self._get_record(user_id)
        if record is None:
            raise ValueError(f"No billing record found for user {user_id}")

        old_plan = record.plan_type
        now = time.time()

        # Update Stripe subscription
        if self._stripe and record.stripe_subscription_id:
            try:
                import os
                price_map = {
                    "starter": os.environ.get("STRIPE_STARTER_PRICE_ID", ""),
                    "business": os.environ.get("STRIPE_BUSINESS_PRICE_ID", ""),
                    "enterprise": os.environ.get("STRIPE_ENTERPRISE_PRICE_ID", ""),
                }
                new_price_id = price_map.get(new_plan.value, "")
                if new_price_id:
                    import asyncio
                    asyncio.get_event_loop().run_until_complete(
                        self._stripe.update_subscription(
                            record.stripe_subscription_id,
                            new_price_id,
                        )
                    )
            except Exception as exc:
                logger.warning("SubscriptionManager: Stripe plan change failed: %s", exc)

        record.plan_type = new_plan
        record.status = SubscriptionStatus.ACTIVE
        record.updated_at = now
        self._save_record(record)

        self._log_event(BillingEvent(
            event_type="plan_changed",
            timestamp=now,
            plan=new_plan.value,
            amount=new_plan.monthly_price,
            user_id=user_id,
            metadata={
                "old_plan": old_plan.value if isinstance(old_plan, BillingPlan) else old_plan,
                "new_plan": new_plan.value,
                "proration": True,
            },
        ))

        logger.info("SubscriptionManager: plan changed for %s (%s → %s)", user_id, old_plan, new_plan)
        return record

    # ── Feature access checking ────────────────────────────

    def check_access(self, user_id: str, feature: str) -> Tuple[bool, str]:
        """Check if user has access to a feature.

        Args:
            user_id: User/tenant identifier.
            feature: Feature name (e.g. 'api_access', 'webhooks', 'sso').

        Returns:
            Tuple of (allowed: bool, reason: str).
        """
        record = self._get_record(user_id)
        if record is None:
            return False, f"No billing record for user {user_id}"

        # Check if trial expired → degraded access
        if record.status == SubscriptionStatus.TRIAL:
            if record.trial_end and time.time() > record.trial_end:
                return self._degraded_access(user_id)

        plan_name = record.plan_type.value if isinstance(record.plan_type, BillingPlan) else record.plan_type
        limits = PLAN_LIMITS.get(plan_name, PLAN_LIMITS["free"])

        # Check specific feature
        if feature in limits:
            allowed = limits[feature]
            if isinstance(allowed, bool):
                if not allowed:
                    return False, f"Feature '{feature}' not available on {plan_name} plan. Upgrade required."
                return True, "Access granted"
            return True, "Access granted"

        # Feature not in limits dict — check usage-based features
        if feature in ("actions", "actions_per_day"):
            usage = self.get_usage(user_id)
            for u in usage:
                if u.feature_name == "actions":
                    if u.is_over_limit:
                        return False, f"Daily action limit reached ({u.usage_count}/{u.limit})"
                    return True, "Access granted"

        # Default: allow for active subscriptions, deny for inactive
        if SubscriptionStatus.is_active_status(record.status):
            return True, "Access granted"

        return self._degraded_access(user_id)

    def _degraded_access(self, user_id: str) -> Tuple[bool, str]:
        """Return limited access info for expired trial / cancelled subscription.

        Returns:
            Tuple of (False, reason_message).
        """
        record = self._get_record(user_id)
        plan_name = "free"
        if record:
            plan_name = record.plan_type.value if isinstance(record.plan_type, BillingPlan) else record.plan_type

        return False, (
            f"Your trial has expired. Current plan: {plan_name}. "
            "Upgrade to continue using premium features."
        )

    # ── Usage tracking ─────────────────────────────────────

    def get_usage(self, user_id: str) -> List[UsageRecord]:
        """Get current usage vs limits for a user.

        Returns usage records for the current billing period.
        """
        record = self._get_record(user_id)
        plan_name = "free"
        if record:
            plan_name = record.plan_type.value if isinstance(record.plan_type, BillingPlan) else record.plan_type
        limits = PLAN_LIMITS.get(plan_name, PLAN_LIMITS["free"])

        now = time.time()
        # Calculate current period
        if record and record.current_period_start:
            period_start = record.current_period_start
            period_end = record.current_period_end or (period_start + 30 * 86400)
        else:
            # Default: current day
            period_start = now - (now % 86400)
            period_end = period_start + 86400

        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT feature_name, usage_count, period_start, period_end "
                "FROM usage_records WHERE tenant_id = ? AND period_start >= ?",
                (user_id, period_start),
            ).fetchall()
        except sqlite3.Error as e:
            logger.error("SubscriptionManager: get_usage error: %s", e)
            return []
        finally:
            conn.close()

        # Build usage map from DB
        usage_map: Dict[str, int] = {}
        for row in rows:
            usage_map[row["feature_name"]] = row["usage_count"]

        # Build result with limits
        result: List[UsageRecord] = []
        feature_limits = {
            "actions": limits.get("actions_per_day", 100),
            "monitors": limits.get("monitors", 5),
            "users": limits.get("users", 1),
        }
        for feature, limit in feature_limits.items():
            result.append(UsageRecord(
                feature_name=feature,
                usage_count=usage_map.get(feature, 0),
                limit=limit,
                period_start=period_start,
                period_end=period_end,
            ))

        return result

    def record_usage(
        self,
        user_id: str,
        feature: str,
        increment: int = 1,
    ) -> UsageRecord:
        """Record feature usage for a user.

        Args:
            user_id: User/tenant identifier.
            feature: Feature name (e.g. 'actions', 'monitors').
            increment: Amount to add (default 1).

        Returns:
            Updated UsageRecord.
        """
        record = self._get_record(user_id)
        plan_name = "free"
        if record:
            plan_name = record.plan_type.value if isinstance(record.plan_type, BillingPlan) else record.plan_type
        limits = PLAN_LIMITS.get(plan_name, PLAN_LIMITS["free"])

        now = time.time()
        period_start = now - (now % 86400)
        period_end = period_start + 86400

        feature_limits = {
            "actions": limits.get("actions_per_day", 100),
            "monitors": limits.get("monitors", 5),
            "users": limits.get("users", 1),
        }
        limit = feature_limits.get(feature, -1)

        conn = self._conn()
        try:
            with self._lock:
                # Upsert usage
                conn.execute(
                    "INSERT INTO usage_records (tenant_id, feature_name, usage_count, period_start, period_end) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(tenant_id, feature_name, period_start) DO UPDATE SET "
                    "usage_count = usage_count + ?",
                    (user_id, feature, increment, period_start, period_end, increment),
                )
                conn.commit()

                row = conn.execute(
                    "SELECT usage_count FROM usage_records "
                    "WHERE tenant_id = ? AND feature_name = ? AND period_start = ?",
                    (user_id, feature, period_start),
                ).fetchone()
                count = row["usage_count"] if row else increment
        except sqlite3.Error as e:
            logger.error("SubscriptionManager: record_usage error: %s", e)
            count = increment
        finally:
            conn.close()

        return UsageRecord(
            feature_name=feature,
            usage_count=count,
            limit=limit,
            period_start=period_start,
            period_end=period_end,
        )

    # ── Trial expiry ───────────────────────────────────────

    def check_trial_expiry(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Check if trial has expired and return degradation info.

        Returns:
            None if trial is active or not in trial.
            Dict with degradation info if trial expired.
        """
        record = self._get_record(user_id)
        if record is None:
            return None

        if record.status != SubscriptionStatus.TRIAL:
            return None

        if record.trial_end and time.time() > record.trial_end:
            # Trial expired — degrade
            now = time.time()
            record.status = SubscriptionStatus.DEGRADED
            record.plan_type = BillingPlan.FREE
            record.updated_at = now
            self._save_record(record)

            self._log_event(BillingEvent(
                event_type="trial_expired",
                timestamp=now,
                plan="free",
                user_id=user_id,
                metadata={"previous_plan": "business"},
            ))

            return {
                "expired": True,
                "tenant_id": user_id,
                "degraded_to": "free",
                "message": "Trial period has expired. Upgrade to continue using premium features.",
            }

        return None

    # ── Webhook event processing ───────────────────────────

    def process_webhook_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Process a Stripe webhook event.

        Handles:
          - checkout.session.completed → activates subscription
          - customer.subscription.updated → updates local record
          - customer.subscription.deleted → handles cancellation
          - invoice.payment_failed → marks past_due
          - invoice.paid → confirms active

        Args:
            event: Parsed Stripe event dict with 'type' and 'data'.

        Returns:
            Dict with 'status' and 'message'.
        """
        event_type = event.get("type", "")
        data = event.get("data", {}).get("object", {})

        logger.info("SubscriptionManager: processing webhook event '%s'", event_type)

        handlers = {
            "checkout.session.completed": self._wh_checkout_completed,
            "customer.subscription.updated": self._wh_subscription_updated,
            "customer.subscription.deleted": self._wh_subscription_deleted,
            "invoice.payment_failed": self._wh_payment_failed,
            "invoice.paid": self._wh_invoice_paid,
            "invoice.payment_action_required": self._wh_payment_action_required,
        }

        handler = handlers.get(event_type)
        if handler:
            try:
                return handler(data)
            except Exception as exc:
                logger.error("SubscriptionManager: webhook handler error for '%s': %s", event_type, exc)
                return {"status": "error", "message": str(exc)}

        # Unhandled event types are acknowledged
        return {"status": "acknowledged", "message": f"Unhandled event type: {event_type}"}

    def _wh_checkout_completed(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Activate subscription after successful checkout."""
        metadata = data.get("metadata", {})
        tenant_id = metadata.get("tenant_id", "")
        plan_str = metadata.get("plan_type", "business")
        customer_id = data.get("customer", "")
        subscription_id = data.get("subscription", "")

        if not tenant_id:
            return {"status": "error", "message": "Missing tenant_id in checkout metadata"}

        try:
            plan = BillingPlan(plan_str)
        except ValueError:
            plan = BillingPlan.BUSINESS

        record = self._get_record(tenant_id)
        now = time.time()
        if record is None:
            record = BillingRecord(
                tenant_id=tenant_id,
                created_at=now,
                updated_at=now,
            )

        record.status = SubscriptionStatus.ACTIVE
        record.plan_type = plan
        record.stripe_customer_id = customer_id or record.stripe_customer_id
        record.stripe_subscription_id = subscription_id or record.stripe_subscription_id
        record.current_period_start = now
        record.current_period_end = now + (30 * 86400)
        record.updated_at = now
        self._save_record(record)

        self._log_event(BillingEvent(
            event_type="checkout_completed",
            timestamp=now,
            plan=plan.value,
            user_id=tenant_id,
            metadata={"customer_id": customer_id, "subscription_id": subscription_id},
        ))

        return {"status": "ok", "message": "Subscription activated"}

    def _wh_subscription_updated(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update local subscription record from Stripe."""
        subscription_id = data.get("id", "")
        customer_id = data.get("customer", "")

        # Find record by stripe_subscription_id
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM billing_records WHERE stripe_subscription_id = ?",
                (subscription_id,),
            ).fetchone()
        except sqlite3.Error as e:
            logger.error("SubscriptionManager: _wh_subscription_updated error: %s", e)
            return {"status": "error", "message": "DB error"}
        finally:
            conn.close()

        if row is None:
            return {"status": "error", "message": f"No record found for subscription {subscription_id}"}

        record = BillingRecord.from_row(dict(row))
        now = time.time()

        # Update from Stripe data
        stripe_status = data.get("status", "")
        status_map = {
            "active": SubscriptionStatus.ACTIVE,
            "trialing": SubscriptionStatus.TRIAL,
            "past_due": SubscriptionStatus.PAST_DUE,
            "canceled": SubscriptionStatus.CANCELED,
            "cancelled": SubscriptionStatus.CANCELLED,
        }
        if stripe_status in status_map:
            record.status = status_map[stripe_status]

        # Update period dates
        period_start = data.get("current_period_start")
        period_end = data.get("current_period_end")
        if period_start:
            record.current_period_start = period_start
        if period_end:
            record.current_period_end = period_end

        record.updated_at = now
        self._save_record(record)

        return {"status": "ok", "message": "Subscription updated"}

    def _wh_subscription_deleted(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle subscription deletion (cancellation)."""
        subscription_id = data.get("id", "")

        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM billing_records WHERE stripe_subscription_id = ?",
                (subscription_id,),
            ).fetchone()
        except sqlite3.Error as e:
            logger.error("SubscriptionManager: _wh_subscription_deleted error: %s", e)
            return {"status": "error", "message": "DB error"}
        finally:
            conn.close()

        if row is None:
            return {"status": "error", "message": f"No record found for subscription {subscription_id}"}

        record = BillingRecord.from_row(dict(row))
        now = time.time()
        record.status = SubscriptionStatus.CANCELED
        record.plan_type = BillingPlan.FREE
        record.updated_at = now
        self._save_record(record)

        self._log_event(BillingEvent(
            event_type="subscription_deleted",
            timestamp=now,
            plan="free",
            user_id=record.tenant_id,
        ))

        return {"status": "ok", "message": "Subscription cancelled"}

    def _wh_payment_failed(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mark subscription as past_due on payment failure."""
        customer_id = data.get("customer", "")

        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM billing_records WHERE stripe_customer_id = ?",
                (customer_id,),
            ).fetchone()
        except sqlite3.Error as e:
            logger.error("SubscriptionManager: _wh_payment_failed error: %s", e)
            return {"status": "error", "message": "DB error"}
        finally:
            conn.close()

        if row is None:
            return {"status": "error", "message": f"No record found for customer {customer_id}"}

        record = BillingRecord.from_row(dict(row))
        now = time.time()
        record.status = SubscriptionStatus.PAST_DUE
        record.updated_at = now
        self._save_record(record)

        self._log_event(BillingEvent(
            event_type="payment_failed",
            timestamp=now,
            plan=record.plan_type.value if isinstance(record.plan_type, BillingPlan) else record.plan_type,
            user_id=record.tenant_id,
        ))

        return {"status": "ok", "message": "Marked past_due"}

    def _wh_invoice_paid(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Confirm active status on successful payment."""
        customer_id = data.get("customer", "")
        subscription_id = data.get("subscription", "")

        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM billing_records WHERE stripe_customer_id = ?",
                (customer_id,),
            ).fetchone()
        except sqlite3.Error as e:
            logger.error("SubscriptionManager: _wh_invoice_paid error: %s", e)
            return {"status": "error", "message": "DB error"}
        finally:
            conn.close()

        if row is None:
            return {"status": "error", "message": f"No record found for customer {customer_id}"}

        record = BillingRecord.from_row(dict(row))
        now = time.time()
        record.status = SubscriptionStatus.ACTIVE
        # Update period end from invoice lines
        lines = data.get("lines", {}).get("data", [])
        if lines:
            period_end = lines[0].get("period", {}).get("end")
            if period_end:
                record.current_period_end = period_end
        record.updated_at = now
        self._save_record(record)

        self._log_event(BillingEvent(
            event_type="invoice_paid",
            timestamp=now,
            plan=record.plan_type.value if isinstance(record.plan_type, BillingPlan) else record.plan_type,
            amount=data.get("amount_paid", 0),
            user_id=record.tenant_id,
        ))

        return {"status": "ok", "message": "Payment confirmed, subscription active"}

    def _wh_payment_action_required(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle SCA (Strong Customer Authentication) requirement."""
        customer_id = data.get("customer", "")
        logger.warning("SubscriptionManager: SCA payment action required for customer %s", customer_id)

        self._log_event(BillingEvent(
            event_type="payment_action_required",
            timestamp=time.time(),
            plan="",
            user_id=customer_id,
            metadata={"sca_required": True},
        ))

        return {"status": "ok", "message": "SCA action required notification logged"}

    # ── Convenience methods ────────────────────────────────

    def get_status(self, tenant_id: str) -> Optional[BillingRecord]:
        """Get the billing record for a tenant (alias for _get_record)."""
        return self._get_record(tenant_id)

    def get_invoices(self, tenant_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get invoice history for a tenant from billing events."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM billing_events WHERE user_id = ? "
                "AND event_type IN ('invoice_paid', 'payment_failed', 'checkout_completed') "
                "ORDER BY timestamp DESC LIMIT ?",
                (tenant_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as e:
            logger.error("SubscriptionManager: get_invoices error: %s", e)
            return []
        finally:
            conn.close()

    def activate_subscription_compat(
        self,
        tenant_id: str,
        stripe_customer_id: str,
        stripe_subscription_id: str,
        plan: BillingPlan,
    ) -> BillingRecord:
        """Backward-compatible activation (used by TrialManager + WebhookHandler).

        Sets Stripe IDs directly and activates without requiring a payment_method_id.
        """
        record = self._get_record(tenant_id)
        if record is None:
            now = time.time()
            record = BillingRecord(
                tenant_id=tenant_id,
                created_at=now,
                updated_at=now,
            )

        now = time.time()
        record.status = SubscriptionStatus.ACTIVE
        record.plan_type = plan
        record.stripe_customer_id = stripe_customer_id or record.stripe_customer_id
        record.stripe_subscription_id = stripe_subscription_id or record.stripe_subscription_id
        record.current_period_start = now
        record.current_period_end = now + (30 * 86400)
        record.cancel_at_period_end = False
        record.updated_at = now
        self._save_record(record)

        self._log_event(BillingEvent(
            event_type="subscription_activated",
            timestamp=now,
            plan=plan.value,
            user_id=tenant_id,
        ))

        return record
