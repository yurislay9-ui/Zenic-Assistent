"""
Zenic-Agents - Exception Engine (Phase C2)

Central exception engine that unifies all exception signals across the
system.  Provides SQLite-backed persistence with retry logic, thread-safe
operations, auto-brake detection, and integration hooks for wiring to
DegradedModeManager, AlertManager, ConfidenceEstimator, etc.
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
from typing import Any, Callable, Dict, List, Optional

from .taxonomy import (
    ExceptionCategory,
    ExceptionSeverity,
    categorize_error,
    severity_from_confidence,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ExceptionSignal",
    "ExceptionRecord",
    "ExceptionEngine",
    "get_exception_engine",
    "reset_exception_engine",
]

# ── Retry helper ──────────────────────────────────────────────

_MAX_RETRIES = 3
_BASE_DELAY = 0.1  # seconds


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
                "ExceptionEngine: DB retry %d/%d after %.2fs – %s",
                attempt + 1, _MAX_RETRIES, delay, exc,
            )
            time.sleep(delay)
        except sqlite3.Error as exc:
            last_exc = exc
            delay = _BASE_DELAY * (2 ** attempt)
            logger.warning(
                "ExceptionEngine: DB error retry %d/%d – %s",
                attempt + 1, _MAX_RETRIES, exc,
            )
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc  # type: ignore[misc]


# ── Dataclasses ───────────────────────────────────────────────


@dataclass
class ExceptionSignal:
    """An immutable snapshot of an exception event flowing through the system."""

    signal_id: str = ""
    source: str = ""
    category: ExceptionCategory = ExceptionCategory.SYSTEM_ERROR
    severity: ExceptionSeverity = ExceptionSeverity.ERROR
    message: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.signal_id:
            self.signal_id = f"sig-{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "signal_id": self.signal_id,
            "source": self.source,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "context": self.context,
            "timestamp": self.timestamp,
        }


@dataclass
class ExceptionRecord:
    """A persisted record linking a signal to its routing outcome."""

    record_id: str = ""
    signal: Optional[ExceptionSignal] = None
    routing_action: str = ""
    resolved: bool = False
    resolved_at: str = ""
    resolution_note: str = ""

    def __post_init__(self) -> None:
        if not self.record_id:
            self.record_id = f"rec-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "record_id": self.record_id,
            "signal": self.signal.to_dict() if self.signal else None,
            "routing_action": self.routing_action,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at,
            "resolution_note": self.resolution_note,
        }


# ── Schema DDL ────────────────────────────────────────────────

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS _zenic_exceptions (
    record_id       TEXT PRIMARY KEY,
    signal_id       TEXT NOT NULL,
    source          TEXT NOT NULL,
    category        TEXT NOT NULL,
    severity        TEXT NOT NULL,
    message         TEXT NOT NULL,
    context_json    TEXT NOT NULL DEFAULT '{}',
    timestamp       TEXT NOT NULL,
    routing_action  TEXT NOT NULL DEFAULT '',
    resolved        INTEGER NOT NULL DEFAULT 0,
    resolved_at     TEXT NOT NULL DEFAULT '',
    resolution_note TEXT NOT NULL DEFAULT '',
    tenant_id       TEXT NOT NULL DEFAULT ''
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_zenic_exc_timestamp
    ON _zenic_exceptions(timestamp);
CREATE INDEX IF NOT EXISTS idx_zenic_exc_category
    ON _zenic_exceptions(category);
CREATE INDEX IF NOT EXISTS idx_zenic_exc_resolved
    ON _zenic_exceptions(resolved);
CREATE INDEX IF NOT EXISTS idx_zenic_exc_tenant
    ON _zenic_exceptions(tenant_id);
"""


# ── Engine ────────────────────────────────────────────────────


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
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
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
        """Create and register an exception signal.

        Returns the created :class:`ExceptionSignal`.  The signal is
        persisted as part of an :class:`ExceptionRecord` and all
        registered callbacks are notified.
        """
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
            conn.execute(
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
                rows = conn.execute(
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
                rows = conn.execute(
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
        """Mark an exception record as resolved.

        Returns ``True`` if the record was found and updated.
        """
        now = datetime.now(timezone.utc).isoformat()

        def _update(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute(
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
        """Return ``True`` if more than *threshold* exceptions occurred in the window.

        This is used by callers to decide whether to engage auto-brake
        (e.g. pause automation, enter degraded mode).
        """
        cutoff = datetime.now(timezone.utc).timestamp() - window_seconds

        def _count(conn: sqlite3.Connection) -> int:
            row = conn.execute(
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
            for row in conn.execute(
                "SELECT category, COUNT(*) FROM _zenic_exceptions "
                "WHERE resolved = 0 GROUP BY category"
            ):
                by_category[row[0]] = row[1]

            by_severity: Dict[str, int] = {}
            for row in conn.execute(
                "SELECT severity, COUNT(*) FROM _zenic_exceptions "
                "WHERE resolved = 0 GROUP BY severity"
            ):
                by_severity[row[0]] = row[1]

            total = conn.execute(
                "SELECT COUNT(*) FROM _zenic_exceptions WHERE resolved = 0"
            ).fetchone()[0]

            # Recent rate: exceptions in the last hour
            one_hour_ago = datetime.now(timezone.utc).timestamp() - 3600
            recent = conn.execute(
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
        """Register a callback invoked whenever a new signal is created.

        Callbacks are called *after* the signal is persisted.  Exceptions
        raised by callbacks are logged but do not interrupt the flow.
        """
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
        """Bridge from :class:`ConfidenceEstimator`.

        If confidence is low enough to warrant a signal, one is created;
        otherwise an INFO-level signal is still registered for observability.
        """
        return self.signal_from_confidence(source, confidence, message, context)

    def feed_alert(self, alert_data: Dict[str, Any]) -> ExceptionSignal:
        """Bridge from :class:`AlertManager`.

        Accepts an alert dictionary and converts it into an exception signal.
        """
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
        row: tuple,  # (record_id, signal_id, source, category, severity, message, context_json, timestamp, routing_action, resolved, resolved_at, resolution_note)
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

_engine_instance: Optional[ExceptionEngine] = None
_engine_lock = threading.Lock()


def get_exception_engine(db_path: str = "exception_engine.sqlite") -> ExceptionEngine:
    """Get or create the global :class:`ExceptionEngine` instance."""
    global _engine_instance
    with _engine_lock:
        if _engine_instance is None:
            _engine_instance = ExceptionEngine(db_path=db_path)
        return _engine_instance


def reset_exception_engine() -> None:
    """Reset the global :class:`ExceptionEngine` (for testing)."""
    global _engine_instance
    with _engine_lock:
        _engine_instance = None
