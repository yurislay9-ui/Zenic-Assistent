"""Core logic for engine."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from ..taxonomy import (
    ExceptionCategory,
    ExceptionSeverity,
    categorize_error,
    severity_from_confidence,
)
from ._types import *
from ._helpers import *

logger = logging.getLogger(__name__)


class ExceptionEngine:
    """Central exception engine that unifies all exception signals.

    Features:
        - SQLite persistence for exception records
        - Thread-safe operations via ``_lock``
        - Retry logic on all DB operations (3 retries, exponential backoff)
        - Auto-brake detection (exception rate threshold)
        - Integration hooks via ``on_signal()`` callbacks
        - Bridge methods from ConfidenceEstimator and AlertManager
    """

    def __init__(self, db_path: str = "exception_engine.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._on_signal_callbacks: List[Callable[[ExceptionSignal], None]] = []
        self._init_db()

    # ── DB initialisation ─────────────────────────────────

    def _init_db(self) -> None:
        """Create tables and indexes (idempotent)."""
        def _exec(conn: sqlite3.Connection) -> None:
            conn.executescript(_CREATE_TABLE_SQL + _CREATE_INDEX_SQL)
            conn.commit()

        _retry_db(self._with_conn, _exec)

    def _with_conn(self, fn: Callable[[sqlite3.Connection], Any]) -> Any:
        """Open a connection, execute *fn*, close the connection."""
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")  # nosemgrep: sqlalchemy-execute-raw-query
        conn.execute("PRAGMA busy_timeout=5000")  # nosemgrep: sqlalchemy-execute-raw-query
        try:
            return fn(conn)
        finally:
            conn.close()

    # ── Signal creation ───────────────────────────────────

    def signal(
        self,
        source: str,
        category: ExceptionCategory,
        severity: ExceptionSeverity,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExceptionSignal:
        """Create and register an exception signal."""
        # Coerce string arguments to enum instances
        if isinstance(category, str):
            category = ExceptionCategory(category)
        if isinstance(severity, str):
            severity = ExceptionSeverity(severity)

        sig = ExceptionSignal(
            source=source,
            category=category,
            severity=severity,
            message=message,
            context=context or {},
        )

        record = ExceptionRecord(signal=sig)

        def _persist(conn: sqlite3.Connection) -> None:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                INSERT INTO _zenic_exceptions
                    (record_id, signal_id, source, category, severity,
                     message, context_json, timestamp, routing_action,
                     resolved, resolved_at, resolution_note, tenant_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    sig.signal_id,
                    sig.source,
                    sig.category.value,
                    sig.severity.value,
                    sig.message,
                    json.dumps(sig.context, default=str),
                    sig.timestamp,
                    record.routing_action,
                    int(record.resolved),
                    record.resolved_at,
                    record.resolution_note,
                    sig.context.get("tenant_id", ""),
                ),
            )
            conn.commit()

        with self._lock:
            _retry_db(self._with_conn, _persist)

        self._fire_callbacks(sig)
        logger.info(
            "ExceptionEngine: signal %s [%s:%s] from %s – %s",
            sig.signal_id, sig.category.value, sig.severity.value,
            sig.source, sig.message[:120],
        )
        return sig

    def signal_from_confidence(
        self,
        source: str,
        confidence: float,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExceptionSignal:
        """Convenience: derive category and severity from a confidence score."""
        category = ExceptionCategory.LOW_CONFIDENCE
        severity = severity_from_confidence(confidence)
        ctx = context or {}
        ctx["confidence_score"] = confidence
        return self.signal(source, category, severity, message, ctx)

    def signal_from_error(
        self,
        source: str,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExceptionSignal:
        """Convenience: derive category from a Python exception."""
        category = categorize_error(error)
        severity = ExceptionSeverity.ERROR
        if category in (
            ExceptionCategory.SECURITY_VIOLATION,
            ExceptionCategory.RESOURCE_EXHAUSTED,
        ):
            severity = ExceptionSeverity.CRITICAL
        ctx = context or {}
        ctx["error_type"] = type(error).__name__
        ctx["error_args"] = list(error.args)
        return self.signal(source, category, severity, str(error), ctx)

    # ── Query ─────────────────────────────────────────────

    def get_active_exceptions(self, tenant_id: str = "") -> List[ExceptionRecord]:
        """Return unresolved exception records, optionally filtered by tenant."""
        def _query(conn: sqlite3.Connection) -> List[ExceptionRecord]:
            if tenant_id:
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """
                    SELECT record_id, signal_id, source, category, severity,
                           message, context_json, timestamp, routing_action,
                           resolved, resolved_at, resolution_note
                    FROM _zenic_exceptions
                    WHERE resolved = 0 AND tenant_id = ?
                    ORDER BY timestamp DESC
                    """,
                    (tenant_id,),
                ).fetchall()
            else:
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """
                    SELECT record_id, signal_id, source, category, severity,
                           message, context_json, timestamp, routing_action,
                           resolved, resolved_at, resolution_note
                    FROM _zenic_exceptions
                    WHERE resolved = 0
                    ORDER BY timestamp DESC
                    """,
                ).fetchall()
            return [self._row_to_record(r) for r in rows]

        return _retry_db(self._with_conn, _query)

    # ── Resolution ────────────────────────────────────────

    def resolve_exception(self, record_id: str, note: str = "") -> bool:
        """Mark an exception record as resolved."""
        now = datetime.now(timezone.utc).isoformat()

        def _update(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                UPDATE _zenic_exceptions
                SET resolved = 1, resolved_at = ?, resolution_note = ?
                WHERE record_id = ? AND resolved = 0
                """,
                (now, note, record_id),
            )
            conn.commit()
            return cursor.rowcount > 0

        with self._lock:
            return _retry_db(self._with_conn, _update)

    # ── Auto-brake ────────────────────────────────────────

    def check_auto_brake(
        self,
        window_seconds: int = 300,
        threshold: int = 3,
    ) -> bool:
        """Return True if more than *threshold* exceptions occurred in the window."""
        cutoff = datetime.now(timezone.utc).timestamp() - window_seconds

        def _count(conn: sqlite3.Connection) -> int:
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                SELECT COUNT(*) FROM _zenic_exceptions
                WHERE resolved = 0
                  AND unixepoch(timestamp) >= ?
                """,
                (cutoff,),
            ).fetchone()
            return row[0] if row else 0

        count = _retry_db(self._with_conn, _count)
        triggered = count > threshold
        if triggered:
            logger.warning(
                "ExceptionEngine: auto-brake triggered – %d exceptions in %ds (threshold=%d)",
                count, window_seconds, threshold,
            )
        return triggered

    # ── Statistics ────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics: counts by category, severity, recent rate."""
        def _collect(conn: sqlite3.Connection) -> Dict[str, Any]:
            by_category: Dict[str, int] = {}
            for row in conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT category, COUNT(*) FROM _zenic_exceptions "
                "WHERE resolved = 0 GROUP BY category"
            ):
                by_category[row[0]] = row[1]

            by_severity: Dict[str, int] = {}
            for row in conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT severity, COUNT(*) FROM _zenic_exceptions "
                "WHERE resolved = 0 GROUP BY severity"
            ):
                by_severity[row[0]] = row[1]

            total = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT COUNT(*) FROM _zenic_exceptions WHERE resolved = 0"
            ).fetchone()[0]

            # Recent rate: exceptions in the last hour
            one_hour_ago = datetime.now(timezone.utc).timestamp() - 3600
            recent = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT COUNT(*) FROM _zenic_exceptions "
                "WHERE unixepoch(timestamp) >= ?",
                (one_hour_ago,),
            ).fetchone()[0]

            return {
                "total_active": total,
                "by_category": by_category,
                "by_severity": by_severity,
                "recent_rate_per_hour": recent,
            }

        return _retry_db(self._with_conn, _collect)

    # ── Callbacks / integration hooks ─────────────────────

    def on_signal(self, callback: Callable[[ExceptionSignal], None]) -> None:
        """Register a callback invoked whenever a new signal is created."""
        self._on_signal_callbacks.append(callback)

    def _fire_callbacks(self, signal: ExceptionSignal) -> None:
        for cb in self._on_signal_callbacks:
            try:
                cb(signal)
            except Exception as exc:
                logger.warning(
                    "ExceptionEngine: on_signal callback error: %s", exc,
                )

    # ── Bridge methods ────────────────────────────────────

    def feed_confidence(
        self,
        source: str,
        confidence: float,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExceptionSignal:
        """Bridge from :class:`ConfidenceEstimator`."""
        return self.signal_from_confidence(source, confidence, message, context)

    def feed_alert(self, alert_data: Dict[str, Any]) -> ExceptionSignal:
        """Bridge from :class:`AlertManager`."""
        source = alert_data.get("monitor_name", alert_data.get("source", "alert_manager"))
        category_str = alert_data.get("category", "SYSTEM_ERROR")
        severity_str = alert_data.get("severity", "ERROR")
        message = alert_data.get("message", alert_data.get("title", "Alert raised"))

        try:
            category = ExceptionCategory(category_str)
        except ValueError:
            category = ExceptionCategory.SYSTEM_ERROR

        try:
            severity = ExceptionSeverity(severity_str)
        except ValueError:
            severity = ExceptionSeverity.ERROR

        ctx = {k: v for k, v in alert_data.items() if k not in ("source", "category", "severity", "message")}
        return self.signal(source, category, severity, message, ctx)

    # ── Row → Record helper ───────────────────────────────

    @staticmethod
    def _row_to_record(
        row: tuple,
    ) -> ExceptionRecord:
        """Convert a DB row tuple to an :class:`ExceptionRecord`."""
        (
            record_id, signal_id, source, category_str,
            severity_str, message, context_json, timestamp,
            routing_action, resolved_int, resolved_at, resolution_note,
        ) = row

        try:
            ctx_data = json.loads(context_json) if context_json else {}
        except (json.JSONDecodeError, TypeError):
            ctx_data = {}

        try:
            category = ExceptionCategory(category_str)
        except ValueError:
            category = ExceptionCategory.SYSTEM_ERROR

        try:
            severity = ExceptionSeverity(severity_str)
        except ValueError:
            severity = ExceptionSeverity.ERROR

        sig = ExceptionSignal(
            signal_id=signal_id,
            source=source,
            category=category,
            severity=severity,
            message=message,
            context=ctx_data,
            timestamp=timestamp,
        )

        return ExceptionRecord(
            record_id=record_id,
            signal=sig,
            routing_action=routing_action,
            resolved=bool(resolved_int),
            resolved_at=resolved_at,
            resolution_note=resolution_note,
        )


# ── Singleton ─────────────────────────────────────────────────
