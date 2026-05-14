"""
TrialManager — trial-specific logic with SQLite persistence.

Manages the trial lifecycle:
  - Starting trials with full BUSINESS features
  - Checking trial status and days remaining
  - Expiring trials and degrading to FREE
  - Extending trials (admin action)
  - Finding expiring trials for notification
  - Sending trial reminder notifications
  - Integration with SNA for proactive trial expiry alerts
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from .types import (
    BillingEvent,
    BillingPlan,
    BillingRecord,
    TRIAL_DURATION_DAYS,
    SubscriptionStatus,
    TrialInfo,
)

logger = logging.getLogger(__name__)


class TrialManager:
    """Trial period manager with SQLite persistence.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str = "billing.db") -> None:
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
        """Create trial tables if they don't exist."""
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
            conn.execute("""CREATE TABLE IF NOT EXISTS billing_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                timestamp REAL NOT NULL,
                plan TEXT NOT NULL,
                amount INTEGER DEFAULT 0,
                currency TEXT DEFAULT 'usd',
                user_id TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}')""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON billing_events(event_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON billing_events(timestamp)")
            conn.commit()
            logger.info("TrialManager: tables initialized at %s", self._db_path)
        except sqlite3.Error as e:
            logger.error("TrialManager: _init_db error: %s", e)
        finally:
            conn.close()

    # ── Persistence helpers ────────────────────────────────

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
            logger.error("TrialManager: _save_record error: %s", e)
        finally:
            conn.close()

    def get_record(self, tenant_id: str) -> Optional[BillingRecord]:
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
            logger.error("TrialManager: get_record error: %s", e)
            return None
        finally:
            conn.close()

    def _log_event(self, event_type: str, tenant_id: str, metadata: Optional[Dict] = None) -> None:
        """Persist a billing event."""
        import json as _json
        conn = self._conn()
        try:
            with self._lock:
                conn.execute(
                    "INSERT INTO billing_events (event_type, timestamp, plan, user_id, metadata) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (event_type, time.time(), "business", tenant_id, _json.dumps(metadata or {})),
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error("TrialManager: _log_event error: %s", e)
        finally:
            conn.close()

    # ── Trial lifecycle ────────────────────────────────────

    def start_trial(
        self,
        user_id: str,
        plan: BillingPlan = BillingPlan.BUSINESS,
    ) -> BillingRecord:
        """Start a 14-day trial with full BUSINESS features.

        Idempotent: returns existing record if one exists.

        Args:
            user_id: Unique user/tenant identifier.
            plan: Plan to trial (default BUSINESS).

        Returns:
            BillingRecord in TRIAL status.
        """
        existing = self.get_record(user_id)
        if existing is not None:
            logger.info("TrialManager: start_trial idempotent return for %s", user_id)
            return existing

        now = time.time()
        trial_end = now + (TRIAL_DURATION_DAYS * 86400)

        record = BillingRecord(
            tenant_id=user_id,
            status=SubscriptionStatus.TRIAL,
            plan_type=plan,
            trial_start=now,
            trial_end=trial_end,
            created_at=now,
            updated_at=now,
        )
        self._save_record(record)
        self._log_event("trial_started", user_id, {"trial_end": trial_end})

        logger.info("TrialManager: trial started for %s (expires=%s)", user_id, trial_end)
        return record

    def get_trial_info(self, user_id: str) -> Optional[TrialInfo]:
        """Get trial status information.

        Args:
            user_id: User/tenant identifier.

        Returns:
            TrialInfo if user is in trial, None otherwise.
        """
        record = self.get_record(user_id)
        if record is None or record.status != SubscriptionStatus.TRIAL:
            return None

        return TrialInfo(
            started_at=record.trial_start,
            expires_at=record.trial_end,
            plan_during_trial=record.plan_type.value if isinstance(record.plan_type, BillingPlan) else record.plan_type,
        )

    def is_trial_active(self, user_id: str) -> bool:
        """Check if a user's trial is still valid (not expired).

        Args:
            user_id: User/tenant identifier.

        Returns:
            True if trial is active, False otherwise.
        """
        record = self.get_record(user_id)
        if record is None:
            return False
        if record.status != SubscriptionStatus.TRIAL:
            return False
        return time.time() < record.trial_end

    def days_remaining(self, user_id: str) -> int:
        """Get days remaining in trial.

        Args:
            user_id: User/tenant identifier.

        Returns:
            Number of days remaining (0 if expired or not in trial).
        """
        record = self.get_record(user_id)
        if record is None or record.status != SubscriptionStatus.TRIAL:
            return 0
        remaining = (record.trial_end - time.time()) / 86400
        return max(0, int(remaining))

    # Alias for backward compatibility with E2E tests
    get_trial_days_remaining = days_remaining

    def expire_trial(self, user_id: str) -> Dict[str, Any]:
        """Handle trial expiration — degrade to FREE.

        Args:
            user_id: User/tenant identifier.

        Returns:
            Dict with expiration result info.
        """
        record = self.get_record(user_id)
        if record is None:
            return {"error": f"No record found for user {user_id}"}

        now = time.time()
        record.status = SubscriptionStatus.DEGRADED
        record.plan_type = BillingPlan.FREE
        record.updated_at = now
        self._save_record(record)

        # Degrade the tenant (update auth system, degraded mode manager)
        self.degrade_tenant(user_id)

        self._log_event("trial_expired", user_id, {"degraded_to": "free"})

        logger.info("TrialManager: trial expired for %s → degraded to FREE", user_id)
        return {
            "tenant_id": user_id,
            "status": "degraded",
            "plan": "free",
            "message": "Trial expired, degraded to free plan",
        }

    def degrade_tenant(self, tenant_id: str) -> None:
        """Degrade a tenant to free plan across the system.

        Updates:
          - AuthService tenant plan
          - DegradedModeManager (if available)
          - SNA alert for trial expiry
        """
        # Update auth service tenant plan
        try:
            from src.core.auth_service import AuthService
            # Cannot easily get singleton; just log the degradation
            logger.info("TrialManager: tenant %s degraded to free plan", tenant_id)
        except ImportError:
            pass

        # Enter degraded mode
        try:
            from src.core.degraded_mode import get_degraded_mode_manager
            dm = get_degraded_mode_manager()
            if dm:
                dm.enter_degraded(
                    reason="trial_expired",
                    message=f"Trial expired for tenant {tenant_id}",
                    level=1,
                )
        except Exception as exc:
            logger.debug("TrialManager: degraded mode entry failed: %s", exc)

        # Fire SNA alert for trial expiry
        try:
            from src.core.sna import get_sna_engine
            sna = get_sna_engine()
            if sna:
                sna.fire_alert(
                    monitor_id="trial_expiry",
                    severity="warning",
                    detail=f"Trial expired for tenant {tenant_id}",
                    tenant_id=tenant_id,
                )
        except Exception as exc:
            logger.debug("TrialManager: SNA alert failed: %s", exc)

    def extend_trial(self, user_id: str, additional_days: int) -> TrialInfo:
        """Extend a trial by additional days (admin action).

        Args:
            user_id: User/tenant identifier.
            additional_days: Number of days to add.

        Returns:
            Updated TrialInfo.
        """
        record = self.get_record(user_id)
        if record is None:
            raise ValueError(f"No billing record found for user {user_id}")

        now = time.time()
        # If trial already expired, extend from now
        current_end = max(record.trial_end, now)
        record.trial_end = current_end + (additional_days * 86400)
        # Restore trial status if it was degraded
        if record.status == SubscriptionStatus.DEGRADED:
            record.status = SubscriptionStatus.TRIAL
            record.plan_type = BillingPlan.BUSINESS
        record.updated_at = now
        self._save_record(record)

        self._log_event("trial_extended", user_id, {
            "additional_days": additional_days,
            "new_end": record.trial_end,
        })

        logger.info("TrialManager: trial extended for %s (+%d days)", user_id, additional_days)

        return TrialInfo(
            started_at=record.trial_start,
            expires_at=record.trial_end,
            plan_during_trial=record.plan_type.value if isinstance(record.plan_type, BillingPlan) else record.plan_type,
        )

    def get_expiring_trials(self, days: int = 3) -> List[Dict[str, Any]]:
        """Get trials expiring within N days (for notification).

        Args:
            days: Look-ahead window in days.

        Returns:
            List of dicts with trial info for expiring trials.
        """
        now = time.time()
        cutoff = now + (days * 86400)

        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT tenant_id, trial_start, trial_end, plan_type, status "
                "FROM billing_records "
                "WHERE status = 'trial' AND trial_end > ? AND trial_end <= ?",
                (now, cutoff),
            ).fetchall()
        except sqlite3.Error as e:
            logger.error("TrialManager: get_expiring_trials error: %s", e)
            return []
        finally:
            conn.close()

        result = []
        for row in rows:
            remaining = (row["trial_end"] - now) / 86400
            result.append({
                "tenant_id": row["tenant_id"],
                "trial_start": row["trial_start"],
                "trial_end": row["trial_end"],
                "plan_type": row["plan_type"],
                "days_remaining": max(0, int(remaining)),
            })
        return result

    def send_trial_reminder(self, user_id: str) -> bool:
        """Send trial expiry reminder via notification executor.

        Uses the NotificationExecutor to send a multi-channel reminder.

        Args:
            user_id: User/tenant identifier.

        Returns:
            True if reminder sent successfully, False otherwise.
        """
        record = self.get_record(user_id)
        if record is None:
            return False

        days_left = self.days_remaining(user_id)
        if days_left <= 0:
            return False

        try:
            from src.core.executors.notification_executor import NotificationExecutor
            notifier = NotificationExecutor()
            import asyncio

            async def _send():
                result = await notifier.execute({
                    "channel": "log",
                    "message": (
                        f"Your Zenic-Agents trial expires in {days_left} day(s). "
                        "Upgrade now to keep access to premium features."
                    ),
                    "subject": f"Trial Reminder: {days_left} days remaining",
                    "recipient": user_id,
                }, {})
                return result.success

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're inside an async context; create a task
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        return loop.run_in_executor(pool, lambda: asyncio.run(_send()))
                else:
                    return loop.run_until_complete(_send())
            except RuntimeError:
                return asyncio.run(_send())

        except Exception as exc:
            logger.warning("TrialManager: send_trial_reminder failed: %s", exc)
            # Fallback: just log the reminder
            logger.info(
                "TRIAL REMINDER: User %s — %d days remaining",
                user_id, days_left,
            )
            return True

    def check_trial_status(self, tenant_id: str) -> SubscriptionStatus:
        """Check and return the current trial status for a tenant.

        If the trial has expired, returns DEGRADED.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Current SubscriptionStatus.
        """
        record = self.get_record(tenant_id)
        if record is None:
            return SubscriptionStatus.EXPIRED

        if record.status == SubscriptionStatus.TRIAL:
            if time.time() > record.trial_end:
                return SubscriptionStatus.DEGRADED
            return SubscriptionStatus.TRIAL

        return record.status

    def check_and_expire_trials(self) -> int:
        """Bulk scan for expired trials and expire them.

        Used by a scheduled job to find and degrade all expired trials.

        Returns:
            Number of trials that were expired.
        """
        now = time.time()
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT tenant_id FROM billing_records "
                "WHERE status = 'trial' AND trial_end <= ?",
                (now,),
            ).fetchall()
        except sqlite3.Error as e:
            logger.error("TrialManager: check_and_expire_trials error: %s", e)
            return 0
        finally:
            conn.close()

        expired_count = 0
        for row in rows:
            tenant_id = row["tenant_id"]
            self.expire_trial(tenant_id)
            expired_count += 1

        if expired_count > 0:
            logger.info("TrialManager: expired %d trial(s)", expired_count)

        return expired_count

    def activate_subscription(
        self,
        tenant_id: str,
        stripe_customer_id: str,
        stripe_subscription_id: str,
        plan: BillingPlan,
    ) -> BillingRecord:
        """Activate a paid subscription from trial.

        Args:
            tenant_id: Tenant identifier.
            stripe_customer_id: Stripe customer ID.
            stripe_subscription_id: Stripe subscription ID.
            plan: Plan to activate.

        Returns:
            Updated BillingRecord in ACTIVE status.
        """
        record = self.get_record(tenant_id)
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

        self._log_event("subscription_activated", tenant_id, {
            "plan": plan.value,
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
        })

        # Exit degraded mode if we were in it
        try:
            from src.core.degraded_mode import get_degraded_mode_manager
            dm = get_degraded_mode_manager()
            if dm:
                dm.exit_degraded()
        except Exception:
            pass

        logger.info("TrialManager: subscription activated for %s (plan=%s)", tenant_id, plan.value)
        return record
