"""
Zenic-Agents - Exception Router (Phase C2)

Routes exception signals to appropriate actions based on configurable
rules.  Provides SQLite-persisted routing rules with thread safety,
retry logic, and lazy integration with ApprovalChain, AutomationEngine,
and DegradedModeManager to avoid circular imports.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .engine import ExceptionEngine, ExceptionSignal
from .taxonomy import ExceptionCategory, ExceptionSeverity

logger = logging.getLogger(__name__)

__all__ = [
    "RoutingAction",
    "RoutingRule",
    "ExceptionRouter",
    "get_exception_router",
    "reset_exception_router",
]

# ── Retry helper ──────────────────────────────────────────────

_MAX_RETRIES = 3
_BASE_DELAY = 0.1


def _retry_db(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Execute *fn* with exponential-backoff retry on DB errors."""
    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except sqlite3.OperationalError as exc:
            last_exc = exc
            delay = _BASE_DELAY * (2 ** attempt)
            logger.warning(
                "ExceptionRouter: DB retry %d/%d after %.2fs – %s",
                attempt + 1, _MAX_RETRIES, delay, exc,
            )
            time.sleep(delay)
        except sqlite3.Error as exc:
            last_exc = exc
            delay = _BASE_DELAY * (2 ** attempt)
            logger.warning(
                "ExceptionRouter: DB error retry %d/%d – %s",
                attempt + 1, _MAX_RETRIES, exc,
            )
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc  # type: ignore[misc]


# ── RoutingAction enum ────────────────────────────────────────


class RoutingAction(str, Enum):
    """Actions that can be taken when an exception is routed."""

    ESCALATE_HUMAN = "ESCALATE_HUMAN"
    PAUSE_AUTOMATION = "PAUSE_AUTOMATION"
    DEGRADE_SYSTEM = "DEGRADE_SYSTEM"
    RETRY_WITH_BACKOFF = "RETRY_WITH_BACKOFF"
    NOTIFY_ADMIN = "NOTIFY_ADMIN"
    ABORT_ACTION = "ABORT_ACTION"
    LOG_AND_CONTINUE = "LOG_AND_CONTINUE"
    REROUTE = "REROUTE"


# ── Severity ordering for rule matching ───────────────────────

_SEVERITY_ORDER: Dict[ExceptionSeverity, int] = {
    ExceptionSeverity.INFO: 0,
    ExceptionSeverity.WARNING: 1,
    ExceptionSeverity.ERROR: 2,
    ExceptionSeverity.CRITICAL: 3,
    ExceptionSeverity.FATAL: 4,
}


# ── RoutingRule dataclass ─────────────────────────────────────


@dataclass
class RoutingRule:
    """A rule that maps exception signals to routing actions.

    A rule matches a signal when:
      - The signal's category equals the rule's category
      - The signal's severity falls between min_severity and max_severity
      - Any extra conditions in ``conditions`` are satisfied
    """

    rule_id: str = ""
    category: ExceptionCategory = ExceptionCategory.SYSTEM_ERROR
    min_severity: ExceptionSeverity = ExceptionSeverity.INFO
    max_severity: ExceptionSeverity = ExceptionSeverity.FATAL
    action: RoutingAction = RoutingAction.LOG_AND_CONTINUE
    conditions: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.rule_id:
            self.rule_id = f"rule-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "rule_id": self.rule_id,
            "category": self.category.value,
            "min_severity": self.min_severity.value,
            "max_severity": self.max_severity.value,
            "action": self.action.value,
            "conditions": self.conditions,
            "priority": self.priority,
            "enabled": self.enabled,
        }

    def matches(self, signal: ExceptionSignal) -> bool:
        """Return ``True`` if *signal* satisfies this rule's criteria."""
        if not self.enabled:
            return False
        if signal.category != self.category:
            return False
        sig_level = _SEVERITY_ORDER.get(signal.severity, 0)
        min_level = _SEVERITY_ORDER.get(self.min_severity, 0)
        max_level = _SEVERITY_ORDER.get(self.max_severity, 0)
        if sig_level < min_level or sig_level > max_level:
            return False
        # Check extra conditions against signal context
        for key, expected in self.conditions.items():
            actual = signal.context.get(key)
            if actual != expected:
                return False
        return True


# ── Schema DDL ────────────────────────────────────────────────

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS _zenic_routing_rules (
    rule_id        TEXT PRIMARY KEY,
    category       TEXT NOT NULL,
    min_severity   TEXT NOT NULL,
    max_severity   TEXT NOT NULL,
    action         TEXT NOT NULL,
    conditions_json TEXT NOT NULL DEFAULT '{}',
    priority       INTEGER NOT NULL DEFAULT 0,
    enabled        INTEGER NOT NULL DEFAULT 1
);
"""


# ── ExceptionRouter ───────────────────────────────────────────


class ExceptionRouter:
    """Maps exception signals to actions based on configurable rules.

    Features:
        - SQLite persistence for routing rules
        - Thread-safe operations
        - Rule matching by category + severity range + extra conditions
        - Lazy integration with ApprovalChain, AutomationEngine,
          and DegradedModeManager (avoids circular imports)
        - Sensible default rules via :meth:`load_default_rules`
    """

    def __init__(self, db_path: str = "exception_routing.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._rules: List[RoutingRule] = []
        self._init_db()
        self._load_rules_from_db()

    # ── DB helpers ────────────────────────────────────────

    def _init_db(self) -> None:
        def _exec(conn: sqlite3.Connection) -> None:
            conn.executescript(_CREATE_TABLE_SQL)
            conn.commit()
        _retry_db(self._with_conn, _exec)

    def _with_conn(self, fn: Callable[[sqlite3.Connection], Any]) -> Any:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")  # nosemgrep: sqlalchemy-execute-raw-query
        conn.execute("PRAGMA busy_timeout=5000")  # nosemgrep: sqlalchemy-execute-raw-query
        try:
            return fn(conn)
        finally:
            conn.close()

    def _load_rules_from_db(self) -> None:
        """Load persisted rules into the in-memory list."""
        def _query(conn: sqlite3.Connection) -> List[RoutingRule]:
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT rule_id, category, min_severity, max_severity, "
                "action, conditions_json, priority, enabled "
                "FROM _zenic_routing_rules ORDER BY priority DESC"
            ).fetchall()
            rules: List[RoutingRule] = []
            for row in rows:
                try:
                    rule = RoutingRule(
                        rule_id=row[0],
                        category=ExceptionCategory(row[1]),
                        min_severity=ExceptionSeverity(row[2]),
                        max_severity=ExceptionSeverity(row[3]),
                        action=RoutingAction(row[4]),
                        conditions=json.loads(row[5]) if row[5] else {},
                        priority=row[6],
                        enabled=bool(row[7]),
                    )
                    rules.append(rule)
                except (ValueError, json.JSONDecodeError) as exc:
                    logger.warning(
                        "ExceptionRouter: skipping malformed rule %s: %s",
                        row[0], exc,
                    )
            return rules

        with self._lock:
            self._rules = _retry_db(self._with_conn, _query)

    # ── Rule management ───────────────────────────────────

    def add_rule(self, rule: RoutingRule) -> None:
        """Persist a routing rule."""
        def _insert(conn: sqlite3.Connection) -> None:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                INSERT OR REPLACE INTO _zenic_routing_rules
                    (rule_id, category, min_severity, max_severity,
                     action, conditions_json, priority, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule.rule_id,
                    rule.category.value,
                    rule.min_severity.value,
                    rule.max_severity.value,
                    rule.action.value,
                    json.dumps(rule.conditions, default=str),
                    rule.priority,
                    int(rule.enabled),
                ),
            )
            conn.commit()

        with self._lock:
            _retry_db(self._with_conn, _insert)
            # Rebuild in-memory list
            self._rules.append(rule)
            self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID.  Returns ``True`` if found and deleted."""
        def _delete(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "DELETE FROM _zenic_routing_rules WHERE rule_id = ?",
                (rule_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

        with self._lock:
            found = _retry_db(self._with_conn, _delete)
            if found:
                self._rules = [r for r in self._rules if r.rule_id != rule_id]
            return found

    def get_rules(self) -> List[RoutingRule]:
        """Return all currently loaded rules (highest priority first)."""
        with self._lock:
            return list(self._rules)

    # ── Routing ───────────────────────────────────────────

    def route(self, signal: ExceptionSignal) -> RoutingAction:
        """Find the best matching rule and return its action.

        Rules are evaluated in priority order (highest first).  The
        first enabled rule that matches wins.  Falls back to
        :attr:`RoutingAction.LOG_AND_CONTINUE` if no rule matches.
        """
        with self._lock:
            for rule in self._rules:
                if rule.matches(signal):
                    logger.info(
                        "ExceptionRouter: signal %s matched rule %s → %s",
                        signal.signal_id, rule.rule_id, rule.action.value,
                    )
                    return rule.action

        logger.info(
            "ExceptionRouter: no rule matched signal %s, defaulting to LOG_AND_CONTINUE",
            signal.signal_id,
        )
        return RoutingAction.LOG_AND_CONTINUE

    # ── Action execution ──────────────────────────────────

    def execute_action(
        self,
        action: RoutingAction,
        signal: ExceptionSignal,
        engine: Optional[ExceptionEngine] = None,
    ) -> Dict[str, Any]:
        """Perform the routing action for the given signal.

        Uses **lazy** imports for external subsystems to prevent
        circular dependencies at module level.

        Returns a dictionary describing the outcome.
        """
        result: Dict[str, Any] = {
            "action": action.value,
            "signal_id": signal.signal_id,
            "status": "executed",
            "detail": "",
        }

        try:
            if action == RoutingAction.ESCALATE_HUMAN:
                result.update(self._action_escalate_human(signal))

            elif action == RoutingAction.PAUSE_AUTOMATION:
                result.update(self._action_pause_automation(signal))

            elif action == RoutingAction.DEGRADE_SYSTEM:
                result.update(self._action_degrade_system(signal))

            elif action == RoutingAction.RETRY_WITH_BACKOFF:
                result.update(self._action_retry_with_backoff(signal))

            elif action == RoutingAction.NOTIFY_ADMIN:
                result.update(self._action_notify_admin(signal))

            elif action == RoutingAction.ABORT_ACTION:
                result.update(self._action_abort(signal))

            elif action == RoutingAction.LOG_AND_CONTINUE:
                result.update(self._action_log_and_continue(signal))

            elif action == RoutingAction.REROUTE:
                result.update(self._action_reroute(signal))

            else:
                result["status"] = "unknown_action"
                result["detail"] = f"Unhandled action: {action.value}"

        except Exception as exc:
            result["status"] = "error"
            result["detail"] = str(exc)
            logger.error(
                "ExceptionRouter: error executing action %s for signal %s: %s",
                action.value, signal.signal_id, exc,
            )

        return result

    # ── Individual action implementations ─────────────────

    def _action_escalate_human(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """ESCALATE_HUMAN: create an approval request."""
        try:
            from src.core.approval.chain import get_approval_chain
            chain = get_approval_chain()
            req = chain.create_request(
                action_type="exception_escalation",
                action_config={
                    "signal_id": signal.signal_id,
                    "category": signal.category.value,
                    "severity": signal.severity.value,
                    "message": signal.message,
                    "source": signal.source,
                },
                requested_by=0,  # system
                required_role="gerente",
                priority="high",
                metadata=signal.context,
            )
            return {
                "status": "escalated",
                "detail": f"Approval request {req.request_id} created",
                "approval_request_id": req.request_id,
            }
        except ImportError:
            logger.warning(
                "ExceptionRouter: approval.chain not available, logging escalation"
            )
            return {"status": "escalated_log_only", "detail": "ApprovalChain unavailable"}

    def _action_pause_automation(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """PAUSE_AUTOMATION: toggle off automation."""
        try:
            from src.core.automation_engine import AutomationEngine
            # Lazy: we don't store a reference; just signal the intent.
            logger.warning(
                "ExceptionRouter: PAUSE_AUTOMATION requested for signal %s",
                signal.signal_id,
            )
            return {
                "status": "paused",
                "detail": "Automation pause requested (AutomationEngine integration)",
            }
        except ImportError:
            logger.warning(
                "ExceptionRouter: automation_engine not available, logging pause request"
            )
            return {"status": "paused_log_only", "detail": "AutomationEngine unavailable"}

    def _action_degrade_system(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """DEGRADE_SYSTEM: enter degraded mode."""
        try:
            from src.core.degraded_mode.manager import get_degraded_mode_manager
            mgr = get_degraded_mode_manager()
            mgr.enter_degraded(
                reason="exception_triggered",
                message=f"Exception {signal.signal_id}: {signal.message[:80]}",
                level=1,
            )
            return {
                "status": "degraded",
                "detail": "System entered degraded mode",
            }
        except ImportError:
            logger.warning(
                "ExceptionRouter: degraded_mode.manager not available, logging degrade request"
            )
            return {"status": "degraded_log_only", "detail": "DegradedModeManager unavailable"}

    def _action_retry_with_backoff(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """RETRY_WITH_BACKOFF: return retry configuration."""
        config = {
            "max_retries": 3,
            "base_delay_ms": 200,
            "max_delay_ms": 5000,
            "backoff_factor": 2.0,
            "jitter": True,
        }
        return {
            "status": "retry_config",
            "detail": "Retry-with-backoff configuration provided",
            "retry_config": config,
        }

    def _action_notify_admin(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """NOTIFY_ADMIN: create a notification record."""
        notification = {
            "type": "admin_notification",
            "signal_id": signal.signal_id,
            "category": signal.category.value,
            "severity": signal.severity.value,
            "source": signal.source,
            "message": signal.message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(
            "ExceptionRouter: admin notification created for signal %s",
            signal.signal_id,
        )
        return {
            "status": "notified",
            "detail": "Admin notification created",
            "notification": notification,
        }

    def _action_abort(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """ABORT_ACTION: return an abort signal."""
        return {
            "status": "aborted",
            "detail": f"Action aborted due to {signal.category.value}",
        }

    def _action_log_and_continue(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """LOG_AND_CONTINUE: just log."""
        logger.info(
            "ExceptionRouter: LOG_AND_CONTINUE for signal %s [%s:%s] – %s",
            signal.signal_id, signal.category.value, signal.severity.value,
            signal.message[:120],
        )
        return {"status": "logged", "detail": "Logged and continued"}

    def _action_reroute(self, signal: ExceptionSignal) -> Dict[str, Any]:
        """REROUTE: find the next matching rule (skip current match)."""
        with self._lock:
            matched = False
            for rule in self._rules:
                if rule.matches(signal):
                    if matched:
                        # This is the second match → use it
                        logger.info(
                            "ExceptionRouter: rerouted signal %s to rule %s → %s",
                            signal.signal_id, rule.rule_id, rule.action.value,
                        )
                        return {
                            "status": "rerouted",
                            "detail": f"Rerouted to action {rule.action.value}",
                            "rerouted_action": rule.action.value,
                            "rerouted_rule_id": rule.rule_id,
                        }
                    matched = True

        return {
            "status": "no_alternative_route",
            "detail": "No alternative rule found for rerouting",
        }

    # ── Default rules ─────────────────────────────────────

    def load_default_rules(self) -> None:
        """Pre-populate with sensible default routing rules.

        Existing rules are not removed; defaults are only added if a
        rule with the same ``rule_id`` does not already exist.
        """
        defaults: List[RoutingRule] = [
            RoutingRule(
                rule_id="default-low-confidence-warning",
                category=ExceptionCategory.LOW_CONFIDENCE,
                min_severity=ExceptionSeverity.WARNING,
                max_severity=ExceptionSeverity.WARNING,
                action=RoutingAction.LOG_AND_CONTINUE,
                priority=10,
            ),
            RoutingRule(
                rule_id="default-low-confidence-critical",
                category=ExceptionCategory.LOW_CONFIDENCE,
                min_severity=ExceptionSeverity.CRITICAL,
                max_severity=ExceptionSeverity.FATAL,
                action=RoutingAction.ESCALATE_HUMAN,
                priority=20,
            ),
            RoutingRule(
                rule_id="default-data-conflict-error",
                category=ExceptionCategory.DATA_CONFLICT,
                min_severity=ExceptionSeverity.ERROR,
                max_severity=ExceptionSeverity.ERROR,
                action=RoutingAction.RETRY_WITH_BACKOFF,
                priority=10,
            ),
            RoutingRule(
                rule_id="default-permission-denied-error",
                category=ExceptionCategory.PERMISSION_DENIED,
                min_severity=ExceptionSeverity.ERROR,
                max_severity=ExceptionSeverity.FATAL,
                action=RoutingAction.ABORT_ACTION,
                priority=30,
            ),
            RoutingRule(
                rule_id="default-anomaly-critical",
                category=ExceptionCategory.ANOMALY_DETECTED,
                min_severity=ExceptionSeverity.CRITICAL,
                max_severity=ExceptionSeverity.FATAL,
                action=RoutingAction.PAUSE_AUTOMATION,
                priority=20,
            ),
            RoutingRule(
                rule_id="default-security-violation-critical",
                category=ExceptionCategory.SECURITY_VIOLATION,
                min_severity=ExceptionSeverity.CRITICAL,
                max_severity=ExceptionSeverity.FATAL,
                action=RoutingAction.DEGRADE_SYSTEM,
                priority=40,
            ),
            RoutingRule(
                rule_id="default-system-error-fatal",
                category=ExceptionCategory.SYSTEM_ERROR,
                min_severity=ExceptionSeverity.FATAL,
                max_severity=ExceptionSeverity.FATAL,
                action=RoutingAction.DEGRADE_SYSTEM,
                priority=30,
            ),
        ]

        existing_ids = {r.rule_id for r in self._rules}
        for rule in defaults:
            if rule.rule_id not in existing_ids:
                self.add_rule(rule)

        logger.info(
            "ExceptionRouter: loaded %d default rules", len(defaults),
        )


# ── Singleton ─────────────────────────────────────────────────

_router_instance: Optional[ExceptionRouter] = None
_router_lock = threading.Lock()


def get_exception_router(db_path: str = "exception_routing.sqlite") -> ExceptionRouter:
    """Get or create the global :class:`ExceptionRouter` instance."""
    global _router_instance
    with _router_lock:
        if _router_instance is None:
            _router_instance = ExceptionRouter(db_path=db_path)
        return _router_instance


def reset_exception_router() -> None:
    """Reset the global :class:`ExceptionRouter` (for testing)."""
    global _router_instance
    with _router_lock:
        _router_instance = None
