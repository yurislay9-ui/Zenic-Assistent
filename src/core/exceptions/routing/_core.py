"""routing — Core implementation (ExceptionRouter class + singleton)."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from typing import Any, Callable, List, Optional

from ._types import *  # noqa: F403
from ._helpers import RoutingActionHelpers

logger = logging.getLogger("zenic_agents.exceptions.routing")


class ExceptionRouter(RoutingActionHelpers):
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
        self._rules: List[RoutingRule] = []  # noqa: F821
        self._init_db()
        self._load_rules_from_db()

    # ── DB helpers ────────────────────────────────────────

    def _init_db(self) -> None:
        def _exec(conn: sqlite3.Connection) -> None:
            conn.executescript(_CREATE_TABLE_SQL)  # noqa: F821
            conn.commit()
        _retry_db(self._with_conn, _exec)  # noqa: F821

    def _with_conn(self, fn: Callable[[sqlite3.Connection], Any]) -> Any:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            return fn(conn)
        finally:
            conn.close()

    def _load_rules_from_db(self) -> None:
        """Load persisted rules into the in-memory list."""
        def _query(conn: sqlite3.Connection) -> List[RoutingRule]:  # noqa: F821
            rows = conn.execute(
                "SELECT rule_id, category, min_severity, max_severity, "
                "action, conditions_json, priority, enabled "
                "FROM _zenic_routing_rules ORDER BY priority DESC"
            ).fetchall()
            rules: List[RoutingRule] = []
            for row in rows:
                try:
                    rule = RoutingRule(
                        rule_id=row[0],
                        category=ExceptionCategory(row[1]),  # noqa: F821
                        min_severity=ExceptionSeverity(row[2]),  # noqa: F821
                        max_severity=ExceptionSeverity(row[3]),  # noqa: F821
                        action=RoutingAction(row[4]),  # noqa: F821
                        conditions=json.loads(row[5]) if row[5] else {},
                        priority=row[6],
                        enabled=bool(row[7]),
                    )
                    rules.append(rule)
                except (ValueError, json.JSONDecodeError) as exc:
                    logger.warning("ExceptionRouter: skipping malformed rule %s: %s", row[0], exc)
            return rules

        with self._lock:
            self._rules = _retry_db(self._with_conn, _query)  # noqa: F821

    # ── Rule management ───────────────────────────────────

    def add_rule(self, rule: RoutingRule) -> None:  # noqa: F821
        """Persist a routing rule."""
        def _insert(conn: sqlite3.Connection) -> None:
            conn.execute(
                """INSERT OR REPLACE INTO _zenic_routing_rules
                    (rule_id, category, min_severity, max_severity,
                     action, conditions_json, priority, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rule.rule_id, rule.category.value,
                    rule.min_severity.value, rule.max_severity.value,
                    rule.action.value,
                    json.dumps(rule.conditions, default=str),
                    rule.priority, int(rule.enabled),
                ),
            )
            conn.commit()

        with self._lock:
            _retry_db(self._with_conn, _insert)  # noqa: F821
            self._rules.append(rule)
            self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID.  Returns ``True`` if found and deleted."""
        def _delete(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute(
                "DELETE FROM _zenic_routing_rules WHERE rule_id = ?",
                (rule_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

        with self._lock:
            found = _retry_db(self._with_conn, _delete)  # noqa: F821
            if found:
                self._rules = [r for r in self._rules if r.rule_id != rule_id]
            return found

    def get_rules(self) -> List[RoutingRule]:  # noqa: F821
        """Return all currently loaded rules (highest priority first)."""
        with self._lock:
            return list(self._rules)

    # ── Routing ───────────────────────────────────────────

    def route(self, signal: ExceptionSignal) -> RoutingAction:  # noqa: F821
        """Find the best matching rule and return its action."""
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
        return RoutingAction.LOG_AND_CONTINUE  # noqa: F821

    # ── Action execution ──────────────────────────────────

    def execute_action(
        self,
        action: RoutingAction,  # noqa: F821
        signal: ExceptionSignal,  # noqa: F821
        engine: Optional[ExceptionEngine] = None,  # noqa: F821
    ) -> Dict[str, Any]:
        """Perform the routing action for the given signal."""
        result: Dict[str, Any] = {
            "action": action.value,
            "signal_id": signal.signal_id,
            "status": "executed",
            "detail": "",
        }

        try:
            if action == RoutingAction.ESCALATE_HUMAN:  # noqa: F821
                result.update(self._action_escalate_human(signal))
            elif action == RoutingAction.PAUSE_AUTOMATION:  # noqa: F821
                result.update(self._action_pause_automation(signal))
            elif action == RoutingAction.DEGRADE_SYSTEM:  # noqa: F821
                result.update(self._action_degrade_system(signal))
            elif action == RoutingAction.RETRY_WITH_BACKOFF:  # noqa: F821
                result.update(self._action_retry_with_backoff(signal))
            elif action == RoutingAction.NOTIFY_ADMIN:  # noqa: F821
                result.update(self._action_notify_admin(signal))
            elif action == RoutingAction.ABORT_ACTION:  # noqa: F821
                result.update(self._action_abort(signal))
            elif action == RoutingAction.LOG_AND_CONTINUE:  # noqa: F821
                result.update(self._action_log_and_continue(signal))
            elif action == RoutingAction.REROUTE:  # noqa: F821
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

    # ── Default rules ─────────────────────────────────────

    def load_default_rules(self) -> None:
        """Pre-populate with sensible default routing rules."""
        defaults: List[RoutingRule] = [  # noqa: F821
            RoutingRule(
                rule_id="default-low-confidence-warning",
                category=ExceptionCategory.LOW_CONFIDENCE,  # noqa: F821
                min_severity=ExceptionSeverity.WARNING, max_severity=ExceptionSeverity.WARNING,  # noqa: F821
                action=RoutingAction.LOG_AND_CONTINUE, priority=10,  # noqa: F821
            ),
            RoutingRule(
                rule_id="default-low-confidence-critical",
                category=ExceptionCategory.LOW_CONFIDENCE,  # noqa: F821
                min_severity=ExceptionSeverity.CRITICAL, max_severity=ExceptionSeverity.FATAL,  # noqa: F821
                action=RoutingAction.ESCALATE_HUMAN, priority=20,  # noqa: F821
            ),
            RoutingRule(
                rule_id="default-data-conflict-error",
                category=ExceptionCategory.DATA_CONFLICT,  # noqa: F821
                min_severity=ExceptionSeverity.ERROR, max_severity=ExceptionSeverity.ERROR,  # noqa: F821
                action=RoutingAction.RETRY_WITH_BACKOFF, priority=10,  # noqa: F821
            ),
            RoutingRule(
                rule_id="default-permission-denied-error",
                category=ExceptionCategory.PERMISSION_DENIED,  # noqa: F821
                min_severity=ExceptionSeverity.ERROR, max_severity=ExceptionSeverity.FATAL,  # noqa: F821
                action=RoutingAction.ABORT_ACTION, priority=30,  # noqa: F821
            ),
            RoutingRule(
                rule_id="default-anomaly-critical",
                category=ExceptionCategory.ANOMALY_DETECTED,  # noqa: F821
                min_severity=ExceptionSeverity.CRITICAL, max_severity=ExceptionSeverity.FATAL,  # noqa: F821
                action=RoutingAction.PAUSE_AUTOMATION, priority=20,  # noqa: F821
            ),
            RoutingRule(
                rule_id="default-security-violation-critical",
                category=ExceptionCategory.SECURITY_VIOLATION,  # noqa: F821
                min_severity=ExceptionSeverity.CRITICAL, max_severity=ExceptionSeverity.FATAL,  # noqa: F821
                action=RoutingAction.DEGRADE_SYSTEM, priority=40,  # noqa: F821
            ),
            RoutingRule(
                rule_id="default-system-error-fatal",
                category=ExceptionCategory.SYSTEM_ERROR,  # noqa: F821
                min_severity=ExceptionSeverity.FATAL, max_severity=ExceptionSeverity.FATAL,  # noqa: F821
                action=RoutingAction.DEGRADE_SYSTEM, priority=30,  # noqa: F821
            ),
        ]

        existing_ids = {r.rule_id for r in self._rules}
        for rule in defaults:
            if rule.rule_id not in existing_ids:
                self.add_rule(rule)

        logger.info("ExceptionRouter: loaded %d default rules", len(defaults))


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
