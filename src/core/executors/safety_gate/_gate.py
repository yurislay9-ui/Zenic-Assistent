"""
Safety Gate — Core Classes.

Contains ActionRateLimiter and SafetyGate classes.

FIX A2 (Hallazgos #9, #10):
  - Added _denied_actions: Set[str] to track which action_ids were DENY'd
  - confirm_action() now checks _denied_actions and returns False for denied actions
  - approve_action() now checks _denied_actions and returns False for denied actions
  - Added _generate_action_id() for unique action identification (mirrors Rust state.rs)
  - Added is_denied() method
  - Updated get_stats() with denied_actions count
  - check() now generates action_id and stores it in SafetyCheckResult
  - Rate-limited actions are also tracked in _denied_actions
"""

import itertools
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Set

from ._types import SafetyVerdict, ActionCategory, SafetyRule, SafetyCheckResult, SAFETY_RULES

logger = logging.getLogger(__name__)

# Phase 5 — Monotonic counter for generating unique action IDs
# Using itertools.count ensures deterministic, monotonically increasing IDs
# within a process. The counter resets to 1 on module reload.
_action_id_counter = itertools.count(1)


class ActionRateLimiter:
    """Per-action-type rate limiter to prevent abuse."""

    def __init__(
        self,
        max_per_minute: int = 30,
        max_per_hour: int = 200,
        max_destructive_per_hour: int = 10,
        max_financial_per_hour: int = 20,
    ) -> None:
        self._max_per_minute = max_per_minute
        self._max_per_hour = max_per_hour
        self._max_destructive_per_hour = max_destructive_per_hour
        self._max_financial_per_hour = max_financial_per_hour
        self._timestamps: Dict[str, List[float]] = {}
        self._category_timestamps: Dict[ActionCategory, List[float]] = {}
        self._lock = threading.Lock()

    def check(self, action_type: str, category: ActionCategory) -> Optional[str]:
        """Check if action is rate-limited. Returns reason or None."""
        with self._lock:
            # Phase 5: Use time.monotonic() for rate-limiting decisions
            # (deterministic within a process, not wall-clock dependent)
            now = time.monotonic()

            # Per-action rate limit
            key = action_type
            self._timestamps.setdefault(key, [])
            self._timestamps[key] = [t for t in self._timestamps[key] if now - t < 60]
            if len(self._timestamps[key]) >= self._max_per_minute:
                return f"Rate limited: {action_type} exceeded {self._max_per_minute}/min"

            # Category rate limits (check BEFORE appending)
            self._category_timestamps.setdefault(category, [])
            cat_ts = self._category_timestamps[category]
            cat_ts[:] = [t for t in cat_ts if now - t < 3600]

            if category == ActionCategory.DESTRUCTIVE and len(cat_ts) >= self._max_destructive_per_hour:
                return f"Rate limited: destructive actions exceeded {self._max_destructive_per_hour}/hour"
            if category == ActionCategory.FINANCIAL and len(cat_ts) >= self._max_financial_per_hour:
                return f"Rate limited: financial actions exceeded {self._max_financial_per_hour}/hour"
            if len(cat_ts) >= self._max_per_hour:
                return f"Rate limited: {category.value} actions exceeded {self._max_per_hour}/hour"

            # ALL checks passed — now append timestamps
            self._timestamps[key].append(now)
            cat_ts.append(now)
            return None

    def reset(self) -> None:
        """Reset all rate limit counters."""
        self._timestamps.clear()
        self._category_timestamps.clear()


class SafetyGate:
    """Pre-execution safety gate for all executor actions.

    INVARIANT: If SafetyGate returns DENY, the action CANNOT proceed.
    No override mechanism exists. This is by design.

    FIX A2: The DENY invariant is now enforced in confirm_action() and
    approve_action(). If an action_id was recorded as DENY'd, neither
    confirmation nor approval will succeed — mirroring the Rust pybridge
    state.rs behavior exactly.
    """

    def __init__(
        self,
        custom_rules: Optional[List[SafetyRule]] = None,
        rate_limiter: Optional[ActionRateLimiter] = None,
    ) -> None:
        self._rules = list(SAFETY_RULES) + (custom_rules or [])
        self._rate_limiter = rate_limiter or ActionRateLimiter()
        self._confirmations: Dict[str, float] = {}
        self._approvals: Dict[str, str] = {}
        self._denied_actions: Set[str] = set()          # FIX A2 (#10): track denied action_ids
        self._denied_count: int = 0
        self._allowed_count: int = 0

    # ── Action ID generation ─────────────────────────────────
    # Mirrors Rust state.rs generate_action_id()

    @staticmethod
    def _generate_action_id() -> str:
        """Generate a unique action ID for each safety validation.

        Phase 5: Uses monotonic counter for deterministic action IDs
        instead of time.time()*1000. Format: "act_{counter}" — guaranteed
        unique within a process and fully deterministic.
        """
        counter = next(_action_id_counter)
        return f"act_{counter}"

    def check(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> SafetyCheckResult:
        """Run all safety checks for an action."""
        context = context or {}
        action_id = self._generate_action_id()             # FIX A2: unique ID per check
        category = self._classify_action(action_type, config)

        rule_result = self._check_rules(action_type, config)
        if rule_result:
            rule_result.action_id = action_id               # FIX A2: assign action_id
            if rule_result.verdict == SafetyVerdict.DENY:
                self._denied_actions.add(action_id)         # FIX A2: track denied
            return rule_result

        rate_reason = self._rate_limiter.check(action_type, category)
        if rate_reason:
            self._denied_count += 1
            self._denied_actions.add(action_id)             # FIX A2: track rate-limited as denied
            return SafetyCheckResult(
                action_id=action_id,                        # FIX A2: include action_id
                verdict=SafetyVerdict.RATE_LIMITED,
                category=category,
                reason=rate_reason,
                rule_name="rate_limiter",
                risk_score=0.6,
            )

        verdict = self._default_verdict(category)
        if verdict == SafetyVerdict.ALLOW:
            self._allowed_count += 1

        return SafetyCheckResult(
            action_id=action_id,                            # FIX A2: include action_id
            verdict=verdict,
            category=category,
            reason=f"Action classified as {category.value}",
            rule_name="default_category_verdict",
            requires_confirmation=(verdict == SafetyVerdict.CONFIRM),
            requires_approval=(verdict == SafetyVerdict.APPROVE),
            risk_score=self._risk_score(category),
        )

    def confirm_action(self, action_id: str) -> bool:
        """Record user confirmation for an action that required it.

        FIX A2 (#9): DENY INVARIANT — Cannot confirm a DENY'd action.
        Always returns False for actions that received a DENY verdict.
        This mirrors the Rust pybridge state.rs confirm_action() exactly.
        """
        # ── DENY invariant enforcement ─────────────────────────
        if action_id in self._denied_actions:
            logger.warning(
                "SafetyGate: Cannot confirm DENIED action %s — DENY is absolute",
                action_id,
            )
            return False

        self._confirmations[action_id] = time.monotonic()
        logger.info("SafetyGate: Action %s confirmed by user", action_id)
        return True

    def approve_action(self, action_id: str, approver_role: str) -> bool:
        """Record role-based approval for an action that required it.

        FIX A2 (#9): DENY INVARIANT — Cannot approve a DENY'd action.
        Always returns False for actions that received a DENY verdict.
        This mirrors the Rust pybridge state.rs approve_action() exactly.
        """
        # ── DENY invariant enforcement ─────────────────────────
        if action_id in self._denied_actions:
            logger.warning(
                "SafetyGate: Cannot approve DENIED action %s — DENY is absolute",
                action_id,
            )
            return False

        self._approvals[action_id] = approver_role
        logger.info("SafetyGate: Action %s approved by %s", action_id, approver_role)
        return True

    def is_confirmed(self, action_id: str) -> bool:
        """Check if an action has been confirmed."""
        return action_id in self._confirmations

    def is_approved(self, action_id: str) -> bool:
        """Check if an action has been approved."""
        return action_id in self._approvals

    def is_denied(self, action_id: str) -> bool:
        """Check if an action was denied.

        FIX A2 (#10): Enables callers to verify DENY status by action_id,
        mirroring the Rust DENIED_ACTIONS check in state.rs.
        """
        return action_id in self._denied_actions

    def get_stats(self) -> Dict[str, Any]:
        """Get safety gate statistics."""
        return {
            "allowed": self._allowed_count,
            "denied": self._denied_count,
            "denied_actions": len(self._denied_actions),        # FIX A2
            "pending_confirmations": len(self._confirmations),
            "pending_approvals": len(self._approvals),
            "rules_count": len(self._rules),
        }

    def _classify_action(self, action_type: str, config: Dict[str, Any]) -> ActionCategory:
        """Classify action into risk category (deterministic)."""
        action_type_lower = action_type.lower()

        if action_type_lower in ("database", "db", "database_operation"):
            operation = str(config.get("operation", "")).lower()
            query = str(config.get("query", "")).upper()
            if "DELETE" in query or operation == "delete":
                return ActionCategory.DESTRUCTIVE
            if "DROP" in query or "TRUNCATE" in query:
                return ActionCategory.DESTRUCTIVE
            if "INSERT" in query or "UPDATE" in query:
                return ActionCategory.MODERATE
            if "backup" in operation or "script" in operation:
                return ActionCategory.SYSTEM
            return ActionCategory.SAFE

        if action_type_lower in ("email", "send_email"):
            subject = str(config.get("subject", "")).lower()
            body = str(config.get("body", "")).lower()
            combined = subject + " " + body
            if any(kw in combined for kw in ("invoice", "factura", "payment", "pago", "refund")):
                return ActionCategory.FINANCIAL
            return ActionCategory.MODERATE

        if action_type_lower in ("file", "file_operation"):
            operation = str(config.get("operation", "")).lower()
            if operation in ("delete", "move"):
                return ActionCategory.DESTRUCTIVE
            if operation in ("write", "append"):
                return ActionCategory.MODERATE
            return ActionCategory.SAFE

        if action_type_lower in ("schedule",):
            return ActionCategory.SYSTEM

        if action_type_lower in ("notification", "send_notification"):
            return ActionCategory.SAFE

        if action_type_lower in ("http", "http_request", "webhook"):
            method = str(config.get("method", "GET")).upper()
            if method in ("DELETE", "PUT"):
                return ActionCategory.MODERATE
            return ActionCategory.SAFE

        if action_type_lower in ("transform", "data_transform"):
            return ActionCategory.SAFE

        if action_type_lower in ("discord",):
            return ActionCategory.MODERATE

        return ActionCategory.MODERATE

    # SECURITY (A7 fix): Severity ordering so that the most severe
    # matching rule wins when multiple rules match the same action.
    _SEVERITY_ORDER = {
        SafetyVerdict.ALLOW: 0,
        SafetyVerdict.CONFIRM: 1,
        SafetyVerdict.APPROVE: 2,
        SafetyVerdict.RATE_LIMITED: 3,
        SafetyVerdict.DENY: 4,
    }

    @classmethod
    def _escalate_verdict(cls, current: SafetyVerdict, new: SafetyVerdict) -> SafetyVerdict:
        """Return the more severe of two verdicts."""
        if cls._SEVERITY_ORDER.get(new, 0) > cls._SEVERITY_ORDER.get(current, 0):
            return new
        return current

    def _check_rules(
        self, action_type: str, config: Dict[str, Any]
    ) -> Optional[SafetyCheckResult]:
        """Check config against ALL safety rules and return the most severe match.

        SECURITY (A7 fix): Iterates every rule instead of returning on the
        first match. A DENY-rule that appears after a CONFIRM-rule must still
        take effect.
        """
        config_str = self._config_to_searchable(action_type, config)

        worst_result: Optional[SafetyCheckResult] = None
        worst_verdict: SafetyVerdict = SafetyVerdict.ALLOW

        for rule in self._rules:
            if not rule.compiled:
                continue
            if rule.compiled.search(config_str):
                worst_verdict = self._escalate_verdict(worst_verdict, rule.verdict)
                # Keep the SafetyCheckResult associated with the worst verdict so far
                if self._SEVERITY_ORDER.get(rule.verdict, 0) >= self._SEVERITY_ORDER.get(worst_verdict, 0):
                    worst_result = SafetyCheckResult(
                        verdict=worst_verdict,
                        category=rule.category,
                        reason=rule.message,
                        rule_name=rule.name,
                        requires_confirmation=(worst_verdict == SafetyVerdict.CONFIRM),
                        requires_approval=(worst_verdict == SafetyVerdict.APPROVE),
                        risk_score=self._risk_score(rule.category),
                    )

        # Count denied once per action, not once per matching DENY rule
        if worst_verdict == SafetyVerdict.DENY:
            self._denied_count += 1

        return worst_result

    def _config_to_searchable(self, action_type: str, config: Dict[str, Any]) -> str:
        """Convert config to a searchable string for rule matching."""
        parts = [action_type]
        for key, value in config.items():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, (list, tuple)):
                parts.extend(str(v) for v in value)
            else:
                parts.append(str(value))
        return " ".join(parts)

    @staticmethod
    def _default_verdict(category: ActionCategory) -> SafetyVerdict:
        """Default verdict based on action category."""
        defaults = {
            ActionCategory.SAFE: SafetyVerdict.ALLOW,
            ActionCategory.MODERATE: SafetyVerdict.ALLOW,
            ActionCategory.DESTRUCTIVE: SafetyVerdict.CONFIRM,
            ActionCategory.FINANCIAL: SafetyVerdict.APPROVE,
            ActionCategory.SYSTEM: SafetyVerdict.CONFIRM,
        }
        return defaults.get(category, SafetyVerdict.CONFIRM)

    @staticmethod
    def _risk_score(category: ActionCategory) -> float:
        """Risk score based on category."""
        scores = {
            ActionCategory.SAFE: 0.0,
            ActionCategory.MODERATE: 0.3,
            ActionCategory.DESTRUCTIVE: 0.8,
            ActionCategory.FINANCIAL: 0.7,
            ActionCategory.SYSTEM: 0.6,
        }
        return scores.get(category, 0.5)


# ── Global Instance ──────────────────────────────────────

_default_safety_gate: Optional[SafetyGate] = None
_safety_gate_lock = threading.Lock()


# ── DENY Persistence Configuration ─────────────────────────
# When configured, denied action IDs are persisted to disk so they
# survive reset_safety_gate() calls. This enforces the DENY invariant.

_DENY_PERSIST_DIR: Optional[str] = None


def configure_deny_persistence(log_dir: str) -> None:
    """Configure persistent deny-action logging.

    When configured, denied action IDs are written to a file
    so they survive reset_safety_gate() calls. This prevents
    accidental bypass of the DENY invariant.

    Args:
        log_dir: Directory path for the deny-persistence file.
    """
    global _DENY_PERSIST_DIR
    _DENY_PERSIST_DIR = log_dir
    logger.info("SafetyGate: DENY persistence configured at %s", log_dir)


def get_default_safety_gate() -> SafetyGate:
    """Get or create the global SafetyGate instance (double-checked locking).

    If deny-persistence is configured, previously denied actions are
    restored on recreation, preserving the DENY invariant across resets.
    """
    global _default_safety_gate
    if _default_safety_gate is None:
        with _safety_gate_lock:
            if _default_safety_gate is None:
                gate = SafetyGate()
                # Restore denied actions from persistence
                if _DENY_PERSIST_DIR:
                    deny_path = os.path.join(_DENY_PERSIST_DIR, ".safety-denied-actions.json")
                    if os.path.exists(deny_path):
                        try:
                            with open(deny_path, "r") as f:
                                data = json.load(f)
                            for action_id in data.get("denied_actions", []):
                                gate._denied_actions.add(action_id)
                            logger.info(
                                "SafetyGate: Restored %d denied actions from persistence",
                                len(gate._denied_actions),
                            )
                        except Exception as exc:
                            logger.warning("SafetyGate: Failed to restore denied actions: %s", exc)
                _default_safety_gate = gate
    return _default_safety_gate


def reset_safety_gate() -> None:
    """Reset the global SafetyGate (for testing).

    SECURITY: If deny-persistence is configured, denied actions
    are preserved across resets. This prevents accidental bypass
    of the DENY invariant.
    """
    global _default_safety_gate

    # Save denied actions before reset
    if _default_safety_gate is not None and _DENY_PERSIST_DIR:
        denied = list(_default_safety_gate._denied_actions)
        try:
            os.makedirs(_DENY_PERSIST_DIR, exist_ok=True)
            deny_path = os.path.join(_DENY_PERSIST_DIR, ".safety-denied-actions.json")
            with open(deny_path, "w") as f:
                json.dump({"denied_actions": denied, "ts": time.time()}, f)
            logger.info("SafetyGate: Persisted %d denied actions before reset", len(denied))
        except Exception as exc:
            logger.error("SafetyGate: Failed to persist denied actions: %s", exc)

    with _safety_gate_lock:
        _default_safety_gate = None
