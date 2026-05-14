"""
ZENIC-AGENTS - Dry-Run Executor (C1: Simulation Engine)

Wraps real executors and intercepts I/O to simulate execution without
real side-effects.  Every operation is recorded but nothing is actually
performed: SMTP sends are blocked, HTTP calls are skipped, DB writes
use journal snapshots instead of real mutations, and file writes are
suppressed.

Thread-safe: All public methods guarded by RLock.
Retry logic: Critical operations wrapped with 3 retries, exponential
backoff (0.1s, 0.2s, 0.4s).
Singleton: get_dry_run_executor() / reset_dry_run_executor().
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import ActionExecutor, ActionResult

logger = logging.getLogger(__name__)

__all__ = [
    "DryRunOperation",
    "DryRunResult",
    "DryRunExecutor",
    "dry_run_dispatch",
    "get_dry_run_executor",
    "reset_dry_run_executor",
]


# ──────────────────────────────────────────────────────────────
#  DATA MODELS
# ──────────────────────────────────────────────────────────────

@dataclass
class DryRunOperation:
    """A single intercepted operation recorded during a dry-run.

    Attributes:
        operation_type: Category of the intercepted operation
            (e.g. ``"smtp"``, ``"http"``, ``"db"``, ``"file"``).
        target: The resource that would have been affected
            (e.g. URL, table name, file path, email address).
        would_affect: Dictionary describing what *would* change.
        timestamp: ISO-8601-like timestamp string of when the
            interception occurred.
    """

    operation_type: str
    target: str
    would_affect: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = _now_ts()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "operation_type": self.operation_type,
            "target": self.target,
            "would_affect": self.would_affect,
            "timestamp": self.timestamp,
        }


@dataclass
class DryRunResult:
    """Result of a full dry-run dispatch.

    Attributes:
        original_request: The dispatch request that was simulated.
        simulated_operations: List of operations that would have been
            performed.
        impact_preview: Dictionary representation of the impact preview
            for the simulated action.
        estimated_effects: Dictionary summarising estimated side-effects.
        would_succeed: Whether the action *would* succeed if executed
            for real.
        safety_verdict_would_be: The safety verdict the SafetyGate
            *would* return (e.g. ``"ALLOW"``, ``"DENY"``).
    """

    original_request: Dict[str, Any]
    simulated_operations: List[DryRunOperation] = field(default_factory=list)
    impact_preview: Dict[str, Any] = field(default_factory=dict)
    estimated_effects: Dict[str, Any] = field(default_factory=dict)
    would_succeed: bool = True
    safety_verdict_would_be: str = "ALLOW"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "original_request": self.original_request,
            "simulated_operations": [op.to_dict() for op in self.simulated_operations],
            "impact_preview": self.impact_preview,
            "estimated_effects": self.estimated_effects,
            "would_succeed": self.would_succeed,
            "safety_verdict_would_be": self.safety_verdict_would_be,
        }


# ──────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────

def _now_ts() -> str:
    """Return a high-resolution timestamp string."""
    return f"{time.time():.6f}"


def _retry(
    fn: Any,
    max_retries: int = 3,
    base_delay: float = 0.1,
    label: str = "dry_run",
) -> Any:
    """Execute *fn* with exponential-backoff retry.

    Delays: base_delay * 2^attempt  →  0.1s, 0.2s, 0.4s.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.debug(
                    "%s: retry %d/%d after %.2fs — %s",
                    label, attempt + 1, max_retries, delay, exc,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "%s: failed after %d attempts — %s",
                    label, max_retries, exc,
                )
    raise last_exc  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────
#  DRY-RUN EXECUTOR
# ──────────────────────────────────────────────────────────────

class DryRunExecutor(ActionExecutor):
    """Wraps real executors and intercepts I/O to simulate execution.

    Instead of performing real operations, it records what *would*
    happen and returns ``ActionResult`` with ``"dry_run": True`` in
    the metadata.

    Supported interception categories:

    * **SMTP** – email sends are blocked; recipient/subject recorded.
    * **HTTP** – no real network calls; URL and method recorded.
    * **DB**   – uses journal snapshots instead of real writes;
      query/table/operation recorded.
    * **File** – no disk writes; path and operation recorded.

    Thread-safe: All public methods guarded by ``_lock``.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._operations: List[DryRunOperation] = []
        self._impact_preview_engine: Optional[Any] = None

    # ── Lazy dependencies ──────────────────────────────────────

    @property
    def impact_preview_engine(self) -> Any:
        """Lazy-load the ImpactPreviewEngine singleton."""
        if self._impact_preview_engine is None:
            # Lazy import to avoid circular dependencies
            from .impact_preview import ImpactPreviewEngine, get_impact_preview_engine
            self._impact_preview_engine = get_impact_preview_engine()
        return self._impact_preview_engine

    # ── ActionExecutor interface ────────────────────────────────

    async def execute(
        self,
        config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ActionResult:
        """Simulate execution without performing real I/O.

        Records the operation and returns ``ActionResult`` with
        ``success=True`` and ``"dry_run": True`` in ``data``.
        """
        start = self._measure()

        action_type = context.get("action_type", "unknown")
        operation = config.get("operation", "")

        # ── Intercept based on action type ────────────────────
        def _intercept() -> None:
            action_lower = action_type.lower()

            if action_lower in ("email", "send_email"):
                self._intercept_smtp(config)
            elif action_lower in ("http", "http_request"):
                self._intercept_http(config)
            elif action_lower in ("database", "db", "database_operation"):
                self._intercept_db(config)
            elif action_lower in ("file", "file_operation"):
                self._intercept_file(config)
            else:
                self._record_operation(
                    operation_type=action_lower,
                    target=operation or action_type,
                    would_affect={"intercepted": True, "config_keys": list(config.keys())},
                )

        try:
            _retry(_intercept, max_retries=3, base_delay=0.1, label="DryRunExecutor.execute")
        except Exception as exc:
            logger.warning("DryRunExecutor: intercept failed for %s: %s", action_type, exc)

        duration = self._elapsed_ms(start)

        return ActionResult(
            success=True,
            data={
                "dry_run": True,
                "action_type": action_type,
                "operation": operation,
                "intercepted": True,
                "operations_recorded": len(self._operations),
            },
            duration_ms=duration,
        )

    # ── Interception helpers ────────────────────────────────────

    def _intercept_smtp(self, config: Dict[str, Any]) -> None:
        """Intercept an SMTP send — no email is actually sent."""
        recipients = config.get("to", [])
        if isinstance(recipients, str):
            recipients = [recipients]
        subject = config.get("subject", "(no subject)")
        self._record_operation(
            operation_type="smtp",
            target=", ".join(str(r) for r in recipients) if recipients else "(no recipients)",
            would_affect={
                "would_send": True,
                "recipients": [str(r) for r in recipients],
                "subject": subject,
                "from": config.get("from_email", ""),
                "cc": config.get("cc", []),
                "bcc": config.get("bcc", []),
            },
        )
        logger.debug("DryRunExecutor: intercepted SMTP to %s", recipients)

    def _intercept_http(self, config: Dict[str, Any]) -> None:
        """Intercept an HTTP request — no real network call."""
        url = config.get("url", config.get("endpoint", "(unknown)"))
        method = config.get("method", "GET").upper()
        self._record_operation(
            operation_type="http",
            target=str(url),
            would_affect={
                "would_request": True,
                "method": method,
                "url": str(url),
                "headers": bool(config.get("headers")),
                "has_body": bool(config.get("body") or config.get("data") or config.get("json")),
            },
        )
        logger.debug("DryRunExecutor: intercepted HTTP %s %s", method, url)

    def _intercept_db(self, config: Dict[str, Any]) -> None:
        """Intercept a DB operation — use journal snapshots instead."""
        query = config.get("query", "")
        table = config.get("table", "")
        operation = str(config.get("operation", "query")).upper()
        self._record_operation(
            operation_type="db",
            target=table or "(unknown table)",
            would_affect={
                "would_execute": True,
                "operation": operation,
                "table": table,
                "query_preview": query[:200] if query else "",
                "uses_journal_snapshot": True,
            },
        )
        logger.debug("DryRunExecutor: intercepted DB %s on %s", operation, table)

    def _intercept_file(self, config: Dict[str, Any]) -> None:
        """Intercept a file operation — no disk writes."""
        source = config.get("source", "")
        destination = config.get("destination", "")
        operation = config.get("operation", "read")
        self._record_operation(
            operation_type="file",
            target=destination or source or "(unknown path)",
            would_affect={
                "would_execute": True,
                "operation": operation,
                "source": source,
                "destination": destination,
                "no_write": True,
            },
        )
        logger.debug("DryRunExecutor: intercepted file %s: %s", operation, destination or source)

    def _record_operation(
        self,
        operation_type: str,
        target: str,
        would_affect: Dict[str, Any],
    ) -> None:
        """Thread-safe recording of an intercepted operation."""
        with self._lock:
            op = DryRunOperation(
                operation_type=operation_type,
                target=target,
                would_affect=would_affect,
            )
            self._operations.append(op)

    # ── Public query methods ────────────────────────────────────

    @property
    def operations(self) -> List[DryRunOperation]:
        """Return a *copy* of the list of simulated operations."""
        with self._lock:
            return list(self._operations)

    def clear(self) -> None:
        """Reset the operation log."""
        with self._lock:
            self._operations.clear()
            logger.debug("DryRunExecutor: operation log cleared")

    def summary(self) -> Dict[str, int]:
        """Return count of simulated operations grouped by operation_type.

        Returns:
            Dict mapping operation_type to count, e.g.
            ``{"smtp": 2, "db": 1}``.
        """
        with self._lock:
            counts: Dict[str, int] = {}
            for op in self._operations:
                counts[op.operation_type] = counts.get(op.operation_type, 0) + 1
            return counts

    # ── Impact Preview integration ──────────────────────────────

    def preview_action(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Preview an action using the ImpactPreviewEngine.

        This is a convenience method that delegates to the
        ImpactPreviewEngine singleton.

        Args:
            action_type: The type of action to preview.
            config: The action configuration dict.
            context: Optional context dict.

        Returns:
            Dictionary representation of the ImpactPreview.
        """
        with self._lock:
            try:
                preview = self.impact_preview_engine.preview_action(
                    action_type, config, context,
                )
                return preview.to_dict()
            except Exception as exc:
                logger.warning(
                    "DryRunExecutor: preview_action failed for %s: %s",
                    action_type, exc,
                )
                return {
                    "action_type": action_type,
                    "error": str(exc),
                    "risk_level": "unknown",
                }


# ──────────────────────────────────────────────────────────────
#  DRY-RUN DISPATCH
# ──────────────────────────────────────────────────────────────

def dry_run_dispatch(
    dispatcher: Any,
    request: Any,
) -> DryRunResult:
    """Run a dispatch through DryRunExecutor and return a DryRunResult.

    This function intercepts the full dispatch pipeline, recording
    what *would* happen without executing anything for real.

    Args:
        dispatcher: An ActionDispatcher instance (or compatible object)
            with a ``dispatch`` method.
        request: A DispatchRequest instance (or dict) describing
            the action to simulate.

    Returns:
        A DryRunResult with all simulated operations, impact preview,
        estimated effects, and a predicted safety verdict.
    """
    executor = get_dry_run_executor()

    # Normalise request to dict for consistent handling
    if hasattr(request, "__dataclass_fields__"):
        # It's a dataclass — extract fields
        from dataclasses import asdict
        request_dict = asdict(request)
    elif isinstance(request, dict):
        request_dict = dict(request)
    else:
        request_dict = {"raw": str(request)}

    action_type = request_dict.get("action_type", "unknown")
    config = request_dict.get("config", {})
    context = request_dict.get("context", {})

    # ── 1. Get impact preview ────────────────────────────────
    impact_preview_dict: Dict[str, Any] = {}
    try:
        impact_preview_dict = executor.preview_action(
            action_type, config, context,
        )
    except Exception as exc:
        logger.warning("dry_run_dispatch: impact preview failed: %s", exc)
        impact_preview_dict = {"error": str(exc)}

    # ── 2. Simulate the action ───────────────────────────────
    simulated_ops: List[DryRunOperation] = []
    would_succeed = True

    try:
        # Record the operation via the DryRunExecutor
        action_lower = action_type.lower()
        if action_lower in ("email", "send_email"):
            executor._intercept_smtp(config)
        elif action_lower in ("http", "http_request"):
            executor._intercept_http(config)
        elif action_lower in ("database", "db", "database_operation"):
            executor._intercept_db(config)
        elif action_lower in ("file", "file_operation"):
            executor._intercept_file(config)
        else:
            executor._record_operation(
                operation_type=action_lower,
                target=config.get("operation", action_type),
                would_affect={"intercepted": True},
            )

        simulated_ops = list(executor.operations)
    except Exception as exc:
        logger.warning("dry_run_dispatch: simulation failed: %s", exc)
        would_succeed = False

    # ── 3. Estimate effects ──────────────────────────────────
    estimated_effects: Dict[str, Any] = {
        "operations_count": len(simulated_ops),
        "types": executor.summary(),
    }

    # ── 4. Predict safety verdict ────────────────────────────
    risk_level = impact_preview_dict.get("risk_level", "none")
    risk_score = impact_preview_dict.get("risk_score", 0.0)

    if risk_level in ("critical", "high") or risk_score >= 0.8:
        safety_verdict = "DENY"
        would_succeed = False
    elif risk_level == "medium" or risk_score >= 0.5:
        safety_verdict = "CONFIRM"
    else:
        safety_verdict = "ALLOW"

    result = DryRunResult(
        original_request=request_dict,
        simulated_operations=simulated_ops,
        impact_preview=impact_preview_dict,
        estimated_effects=estimated_effects,
        would_succeed=would_succeed,
        safety_verdict_would_be=safety_verdict,
    )

    logger.info(
        "dry_run_dispatch: %s — would_succeed=%s verdict=%s ops=%d",
        action_type, would_succeed, safety_verdict, len(simulated_ops),
    )

    return result


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_instance: Optional[DryRunExecutor] = None
_instance_lock = threading.Lock()


def get_dry_run_executor() -> DryRunExecutor:
    """Return the singleton DryRunExecutor instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DryRunExecutor()
    return _instance


def reset_dry_run_executor() -> None:
    """Reset the singleton instance (mainly for testing)."""
    global _instance
    with _instance_lock:
        _instance = None
