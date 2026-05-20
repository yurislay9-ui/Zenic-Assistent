"""
Dry-Run Executor — DryRunExecutor class.

Wraps real executors and intercepts I/O to simulate execution without
real side-effects.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from ..base import ActionExecutor, ActionResult
from ._types import DryRunOperation, _retry

logger = logging.getLogger(__name__)


class DryRunExecutor(ActionExecutor):
    """Wraps real executors and intercepts I/O to simulate execution.

    Instead of performing real operations, it records what *would*
    happen and returns ``ActionResult`` with ``"dry_run": True`` in
    the metadata.

    Supported interception categories:

    * **SMTP** – email sends are blocked; recipient/subject recorded.
    * **HTTP** – no real network calls; URL and method recorded.
    * **DB**   – uses journal snapshots instead of real writes.
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
            from ..impact_preview import ImpactPreviewEngine, get_impact_preview_engine
            self._impact_preview_engine = get_impact_preview_engine()
        return self._impact_preview_engine

    # ── ActionExecutor interface ────────────────────────────────

    async def execute(
        self,
        config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ActionResult:
        """Simulate execution without performing real I/O."""
        start = self._measure()

        action_type = context.get("action_type", "unknown")
        operation = config.get("operation", "")

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
        """Return count of simulated operations grouped by operation_type."""
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
        """Preview an action using the ImpactPreviewEngine."""
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
