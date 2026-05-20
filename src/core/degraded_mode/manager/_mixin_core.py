"""Core logic for manager."""

from __future__ import annotations
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from .persistence import DegradationPersistence
from .types import DegradationLevel, DegradationReason, DegradationState
from ._types import *

logger = logging.getLogger(__name__)

class DegradedModeManager:
    """Manages feature degradation based on security and billing state.

    Levels:
      NORMAL (0)      — Full functionality
      DEGRADED (1)    — Limited features (no executors, read-only dashboards)
      PARALYSIS_1 (2) — Read-only mode (only viewing, no modifications)
      PARALYSIS_2 (3) — Emergency lockdown (admin-only access)
    """

    def __init__(self, db_path: str = "degraded_mode.sqlite") -> None:
        self._db_path = db_path
        self._persistence = DegradationPersistence(db_path)
        self._state = self._persistence.load_state()
        self._current_mode = self._level_to_system_mode(self._state.level)
        self._transition_history: List[ModeTransition] = []
        self._callbacks: List[Callable[[ModeTransition], None]] = []
        self._lock = threading.RLock()

    # ── Mode mapping helpers ──────────────────────────────

    @staticmethod
    def _level_to_system_mode(level: DegradationLevel) -> SystemMode:
        mapping = {
            DegradationLevel.NORMAL: SystemMode.NORMAL,
            DegradationLevel.DEGRADED: SystemMode.DEGRADED,
            DegradationLevel.PARALYSIS_1: SystemMode.PARALYSIS_L1,
            DegradationLevel.PARALYSIS_2: SystemMode.PARALYSIS_L2,
        }
        return mapping.get(level, SystemMode.DEGRADED)

    @staticmethod
    def _system_mode_to_level(mode: SystemMode) -> DegradationLevel:
        return mode.degradation_level

    # ── Core transitions ──────────────────────────────────

    def enter_degraded(
        self,
        reason: DegradationReason = DegradationReason.TRIAL_EXPIRED,
        message: str = "",
        level: int = 1,
    ) -> DegradationState:
        """Enter degraded mode at the given level (1-3)."""
        target_level = {
            1: DegradationLevel.DEGRADED,
            2: DegradationLevel.PARALYSIS_1,
            3: DegradationLevel.PARALYSIS_2,
        }.get(level, DegradationLevel.DEGRADED)

        with self._lock:
            old_level = self._state.level
            self._state = DegradationState(
                level=target_level,
                reason=reason,
                message=message or f"Entered {target_level.name}",
                entered_at=time.time(),
                restricted_features=_FEATURE_RESTRICTIONS.get(target_level, []),
            )
            self._current_mode = self._level_to_system_mode(target_level)
            self._persistence.save_state(self._state)
            self._persistence.append_history(
                from_level=old_level,
                to_level=target_level,
                reason=reason,
                message=self._state.message,
            )
            transition = ModeTransition(
                from_mode=self._level_to_system_mode(old_level),
                to_mode=self._current_mode,
                reason=reason.value,
            )
            self._transition_history.append(transition)
            self._notify_callbacks(transition)
            logger.warning(
                "DegradedModeManager: %s → %s (%s)",
                old_level.name, target_level.name, reason.value,
            )
        return self._state

    def enter_paralysis(self, level: int = 2) -> DegradationState:
        """Enter paralysis mode (level 2 or 3)."""
        target_level = {
            2: DegradationLevel.PARALYSIS_1,
            3: DegradationLevel.PARALYSIS_2,
        }.get(level, DegradationLevel.PARALYSIS_1)
        return self.enter_degraded(
            reason=DegradationReason.TAMPERING_DETECTED,
            message=f"Paralysis level {target_level.value} activated",
            level=target_level.value,
        )

    def exit_degraded(self) -> DegradationState:
        """Return to NORMAL mode (admin only)."""
        with self._lock:
            old_level = self._state.level
            self._state = DegradationState(
                level=DegradationLevel.NORMAL,
                reason=DegradationReason.NONE,
                message="Returned to normal operation",
                entered_at=time.time(),
                restricted_features=[],
            )
            self._current_mode = SystemMode.NORMAL
            self._persistence.save_state(self._state)
            self._persistence.append_history(
                from_level=old_level,
                to_level=DegradationLevel.NORMAL,
                reason=DegradationReason.NONE,
                message="Returned to normal",
                operator="admin",
            )
            transition = ModeTransition(
                from_mode=self._level_to_system_mode(old_level),
                to_mode=SystemMode.NORMAL,
                reason="License restored",
                operator="admin",
            )
            self._transition_history.append(transition)
            self._notify_callbacks(transition)
            logger.info("DegradedModeManager: Returned to NORMAL")
        return self._state

    # ── State queries ─────────────────────────────────────

    def get_state(self) -> DegradationState:
        """Return the current degradation state."""
        return self._state

    def is_feature_allowed(self, feature: str) -> bool:
        """Check whether *feature* is allowed in the current mode."""
        restricted = self._state.restricted_features
        if not restricted:
            return True
        for blocked in restricted:
            if blocked == "*" or feature.startswith(blocked):
                return False
        return True

    def get_restricted_features(self) -> List[str]:
        """Return the list of currently restricted feature prefixes."""
        return list(self._state.restricted_features)

    # ── Auto-degradation ──────────────────────────────────

    def check_and_auto_degrade(
        self,
        billing_status: Optional[str] = None,
        license_valid: Optional[bool] = None,
    ) -> Optional[DegradationState]:
        """Evaluate billing & license and auto-degrade if needed.

        Returns the new DegradationState if a transition occurred, else None.
        """
        if self._state.level >= DegradationLevel.PARALYSIS_1:
            return None  # Already locked down; only admin can restore

        if license_valid is False:
            return self.enter_degraded(
                reason=DegradationReason.LICENSE_INVALID,
                message="License verification failed",
            )

        if billing_status in ("expired", "past_due"):
            return self.enter_degraded(
                reason=DegradationReason.TRIAL_EXPIRED,
                message=f"Billing status: {billing_status}",
            )

        if billing_status == "payment_failed":
            return self.enter_degraded(
                reason=DegradationReason.PAYMENT_FAILED,
                message="Payment processing failed",
            )

        return None

    def check_exception_degradation(
        self,
        exception_count: int,
        window_seconds: int = 300,
        threshold: int = 5,
    ) -> Optional[DegradationState]:
        """Auto-degrade based on exception count in a time window.
        
        Phase C2: Integration with ExceptionEngine.auto_brake.
        If exception_count >= threshold in the given window, enter degraded mode.
        """
        if self._state.level >= DegradationLevel.PARALYSIS_1:
            return None  # Already locked down
        
        if exception_count >= threshold * 2:
            return self.enter_degraded(
                reason=DegradationReason.TAMPERING_DETECTED,
                message=f"Critical exception rate: {exception_count} in {window_seconds}s",
                level=2,
            )
        
        if exception_count >= threshold:
            return self.enter_degraded(
                reason=DegradationReason.MANUAL,
                message=f"High exception rate: {exception_count} in {window_seconds}s",
                level=1,
            )
        
        return None

    # ── Legacy compatibility ──────────────────────────────

    def enter_restrictive(self, reason: str = "Update pending") -> ModeTransition:
        """Enter restrictive mode (limited writes) — legacy compat."""
        self.enter_degraded(DegradationReason.MANUAL, reason, level=1)
        return self._transition_history[-1] if self._transition_history else ModeTransition(
            from_mode=SystemMode.NORMAL, to_mode=SystemMode.RESTRICTIVE, reason=reason,
        )

    def return_to_normal(
        self, reason: str = "License restored", operator: str = "admin",
    ) -> ModeTransition:
        """Return to normal mode — legacy compat."""
        self.exit_degraded()
        return self._transition_history[-1] if self._transition_history else ModeTransition(
            from_mode=SystemMode.DEGRADED, to_mode=SystemMode.NORMAL, reason=reason,
        )

    def get_current_mode(self) -> SystemMode:
        """Get the current operating mode (legacy compat)."""
        return self._current_mode

    def get_capabilities(self) -> Any:
        """Get the capabilities for the current mode."""
        from .mode_parts.capabilities import MODE_CAPABILITIES
        return MODE_CAPABILITIES.get(
            self._current_mode,
            MODE_CAPABILITIES[SystemMode.DEGRADED],
        )

    def check_action(self, action: str) -> Dict[str, Any]:
        """Check if an action is allowed in the current mode."""
        caps = self.get_capabilities()
        blocked = "*" in caps.blocked_actions or action in caps.blocked_actions
        if not blocked:
            cap = {"read": caps.can_read, "write": caps.can_write,
                   "delete": caps.can_delete, "manage_users": caps.can_manage_users,
                   "change_config": caps.can_change_config,
                   "approve_action": caps.can_approve_actions,
                   "export_data": caps.can_export_data, "import_data": caps.can_import_data,
                   "send_email": caps.can_send_email, "create_invoice": caps.can_create_invoice,
                   "create_payment": caps.can_process_payment,
                   "schedule": caps.can_schedule}.get(action, True)
            blocked = not cap
        if blocked:
            return {"allowed": False,
                    "reason": f"Action '{action}' blocked in {self._current_mode.value} mode",
                    "mode": self._current_mode.value}
        return {"allowed": True, "reason": "", "mode": self._current_mode.value}

    def is_endpoint_allowed(self, endpoint: str) -> bool:
        """Check if an API endpoint is accessible in the current mode."""
        caps = self.get_capabilities()
        if not caps.allowed_endpoints:
            return True
        return any(endpoint.startswith(a) for a in caps.allowed_endpoints)

    def resolve_mode_from_license(self) -> Optional[SystemMode]:
        """Determine the correct mode based on license status."""
        try:
            from src.core.license.manager import get_license_manager
            result = get_license_manager().verify()
            if result.status.value == "active":
                return SystemMode.NORMAL
            if result.status.value in ("grace_period", "expired"):
                return SystemMode.DEGRADED
            if result.status.value == "revoked":
                return SystemMode.PARALYSIS_L3
            return SystemMode.DEGRADED
        except ImportError:
            return None

    # ── Callbacks ─────────────────────────────────────────

    def on_mode_change(self, callback: Callable[[ModeTransition], None]) -> None:
        self._callbacks.append(callback)

    def _notify_callbacks(self, transition: ModeTransition) -> None:
        for cb in self._callbacks:
            try:
                cb(transition)
            except Exception as exc:
                logger.warning("DegradedModeManager: Callback error: %s", exc)

    # ── Status ────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive degraded mode status."""
        return {
            "current_mode": self._current_mode.value,
            "degradation_state": self._state.to_dict(),
            "is_read_only": self._state.level.is_read_only,
            "allows_write": self._state.level.allows_write,
            "allows_delete": self._state.level.allows_delete,
            "restricted_features": self._state.restricted_features,
            "transition_count": len(self._transition_history),
        }

    def get_transition_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent mode transition history from persistence."""
        return self._persistence.get_history(limit)


# ── Singleton ─────────────────────────────────────────────

