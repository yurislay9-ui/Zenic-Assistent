"""
Zenic-Agents Asistente — Trial Manager (Phase 7.6)

14-day trial management with automatic degradation.
Tracks trial start, expiry, and transitions to degraded mode.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TRIAL_DURATION_DAYS = 14
TRIAL_PLAN = "pro"


class TrialStatus(str, Enum):
    """Trial lifecycle states."""
    NOT_STARTED = "not_started"
    ACTIVE = "active"
    EXPIRED = "expired"
    CONVERTED = "converted"
    CANCELLED = "cancelled"


@dataclass
class TrialInfo:
    """Trial session information."""
    tenant_id: str
    status: TrialStatus = TrialStatus.NOT_STARTED
    started_at: float = 0.0
    expires_at: float = 0.0
    converted_at: Optional[float] = None
    trial_plan: str = TRIAL_PLAN
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def days_remaining(self) -> int:
        """Days remaining in trial."""
        if self.status != TrialStatus.ACTIVE:
            return 0
        remaining = (self.expires_at - time.time()) / 86400
        return max(0, int(remaining))

    @property
    def is_expired(self) -> bool:
        """Check if trial has expired."""
        if self.status != TrialStatus.ACTIVE:
            return False
        return time.time() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Serialize trial info."""
        return {
            "tenant_id": self.tenant_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "expires_at": self.expires_at,
            "days_remaining": self.days_remaining,
            "is_expired": self.is_expired,
            "trial_plan": self.trial_plan,
        }


class TrialManager:
    """Manages trial periods with automatic degradation.

    Features:
    - 14-day trial with full Pro plan access
    - Automatic degradation on expiry
    - Integration with DegradedModeManager
    - SQLite persistence for trial state
    - Notification on approaching expiry
    """

    def __init__(
        self,
        db_path: str = "billing_trial.sqlite",
        trial_days: int = TRIAL_DURATION_DAYS,
    ) -> None:
        self._db_path = db_path
        self._trial_days = trial_days
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize trial database."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trials (
                    tenant_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'not_started',
                    started_at REAL NOT NULL DEFAULT 0,
                    expires_at REAL NOT NULL DEFAULT 0,
                    converted_at REAL,
                    trial_plan TEXT DEFAULT 'pro',
                    metadata TEXT DEFAULT '{}'
                )
            """)
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("TrialManager: DB init failed: %s", exc)

    # ── Trial Lifecycle ────────────────────────────────

    def start_trial(self, tenant_id: str, plan: str = TRIAL_PLAN) -> TrialInfo:
        """Start a trial for a tenant."""
        with self._lock:
            existing = self._load_trial(tenant_id)
            if existing and existing.status == TrialStatus.ACTIVE:
                return existing

            now = time.time()
            info = TrialInfo(
                tenant_id=tenant_id,
                status=TrialStatus.ACTIVE,
                started_at=now,
                expires_at=now + (self._trial_days * 86400),
                trial_plan=plan,
            )
            self._save_trial(info)
            logger.info(
                "TrialManager: Started %d-day trial for '%s' (plan=%s)",
                self._trial_days, tenant_id, plan,
            )
            return info

    def convert_trial(self, tenant_id: str, target_plan: str = "pro") -> TrialInfo:
        """Convert a trial to a paid subscription."""
        with self._lock:
            info = self._load_trial(tenant_id)
            if not info or info.status != TrialStatus.ACTIVE:
                logger.warning("TrialManager: No active trial for '%s'", tenant_id)
                return info or TrialInfo(tenant_id=tenant_id)

            info.status = TrialStatus.CONVERTED
            info.converted_at = time.time()
            info.trial_plan = target_plan
            self._save_trial(info)
            logger.info("TrialManager: Trial converted for '%s' → %s", tenant_id, target_plan)
            return info

    def cancel_trial(self, tenant_id: str) -> TrialInfo:
        """Cancel an active trial."""
        with self._lock:
            info = self._load_trial(tenant_id)
            if not info:
                return TrialInfo(tenant_id=tenant_id)
            info.status = TrialStatus.CANCELLED
            self._save_trial(info)
            return info

    # ── Queries ────────────────────────────────────────

    def get_trial(self, tenant_id: str) -> TrialInfo:
        """Get trial info for a tenant."""
        info = self._load_trial(tenant_id)
        if info and info.is_expired and info.status == TrialStatus.ACTIVE:
            self._handle_expiry(info)
        return info or TrialInfo(tenant_id=tenant_id)

    def list_active_trials(self) -> List[TrialInfo]:
        """List all active trials."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM trials WHERE status = 'active' ORDER BY started_at DESC"
            ).fetchall()
            conn.close()
            return [self._row_to_info(r) for r in rows]
        except Exception:
            return []

    def list_expiring_soon(self, days: int = 3) -> List[TrialInfo]:
        """List trials expiring within N days."""
        cutoff = time.time() + (days * 86400)
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM trials WHERE status = 'active' AND expires_at <= ?",
                (cutoff,),
            ).fetchall()
            conn.close()
            return [self._row_to_info(r) for r in rows]
        except Exception:
            return []

    # ── Auto-degradation ───────────────────────────────

    def check_and_degrade(self) -> List[TrialInfo]:
        """Check all trials and degrade expired ones."""
        expired: List[TrialInfo] = []
        for trial in self.list_active_trials():
            if trial.is_expired:
                self._handle_expiry(trial)
                expired.append(trial)
        return expired

    def _handle_expiry(self, info: TrialInfo) -> None:
        """Handle an expired trial by entering degraded mode."""
        info.status = TrialStatus.EXPIRED
        self._save_trial(info)
        logger.info("TrialManager: Trial expired for '%s'", info.tenant_id)

        try:
            from src.core.degraded_mode.manager import get_degraded_mode_manager
            dm = get_degraded_mode_manager()
            dm.enter_degraded(reason=f"Trial expired for tenant '{info.tenant_id}'")
        except ImportError:
            logger.warning("TrialManager: Degraded mode not available")

    # ── Persistence ────────────────────────────────────

    def _load_trial(self, tenant_id: str) -> Optional[TrialInfo]:
        """Load trial from database."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM trials WHERE tenant_id = ?", (tenant_id,),
            ).fetchone()
            conn.close()
            return self._row_to_info(row) if row else None
        except Exception:
            return None

    def _save_trial(self, info: TrialInfo) -> None:
        """Save trial to database."""
        import json
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT OR REPLACE INTO trials
                   (tenant_id, status, started_at, expires_at, converted_at, trial_plan, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (info.tenant_id, info.status.value, info.started_at, info.expires_at,
                 info.converted_at, info.trial_plan, json.dumps(info.metadata)),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("TrialManager: Save failed: %s", exc)

    @staticmethod
    def _row_to_info(row: sqlite3.Row) -> TrialInfo:
        """Convert DB row to TrialInfo."""
        import json
        return TrialInfo(
            tenant_id=row["tenant_id"],
            status=TrialStatus(row["status"]),
            started_at=row["started_at"],
            expires_at=row["expires_at"],
            converted_at=row["converted_at"],
            trial_plan=row["trial_plan"],
            metadata=json.loads(row.get("metadata", "{}")),
        )


# ── Singleton ─────────────────────────────────────────

_trial_manager: Optional[TrialManager] = None
_lock = threading.Lock()


def get_trial_manager(**kwargs: Any) -> TrialManager:
    """Get or create the global TrialManager."""
    global _trial_manager
    with _lock:
        if _trial_manager is None:
            _trial_manager = TrialManager(**kwargs)
        return _trial_manager


def reset_trial_manager() -> None:
    """Reset the global TrialManager (for testing)."""
    global _trial_manager
    _trial_manager = None
