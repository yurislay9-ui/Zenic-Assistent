"""Core logic for analytics."""

from __future__ import annotations
import json
import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from ..engine import ExceptionSignal
from ..taxonomy import ExceptionCategory, ExceptionSeverity
from ._types import *
from ._helpers import *

logger = logging.getLogger(__name__)

class ExceptionAnalytics:
    """Exception analytics engine for pattern detection and dashboards.

    Features:
        - SQLite persistence for signal and pattern data
        - Thread-safe operations via ``_lock``
        - Pattern detection: groups by category+source, computes
          frequency, avg interval, and trend
        - Snapshot generation for dashboards
        - Trend and distribution queries
        - Retry logic on all DB operations
    """

    def __init__(self, db_path: str = "exception_analytics.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    # ── DB helpers ────────────────────────────────────────

    def _init_db(self) -> None:
        def _exec(conn: sqlite3.Connection) -> None:
            conn.executescript(_CREATE_TABLE_SQL + _CREATE_INDEX_SQL)
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

    # ── Recording ─────────────────────────────────────────

    def record_signal(self, signal: ExceptionSignal) -> None:
        """Record an exception signal for analytics.

        Called by :class:`ExceptionEngine` after each signal is created.
        """
        tenant_id = signal.context.get("tenant_id", "")

        def _insert(conn: sqlite3.Connection) -> None:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                INSERT OR IGNORE INTO _zenic_analytics_signals
                    (signal_id, source, category, severity, message,
                     context_json, timestamp, tenant_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.signal_id,
                    signal.source,
                    signal.category.value,
                    signal.severity.value,
                    signal.message,
                    json.dumps(signal.context, default=str),
                    signal.timestamp,
                    tenant_id,
                ),
            )
            conn.commit()

        with self._lock:
            _retry_db(self._with_conn, _insert)

    # ── Snapshot ──────────────────────────────────────────

    def get_snapshot(
        self,
        from_time: str = "",
        to_time: str = "",
        tenant_id: str = "",
    ) -> AnalyticsSnapshot:
        """Generate a point-in-time analytics snapshot.

        Parameters:
            from_time: ISO-8601 start of window (default: 24h ago).
            to_time: ISO-8601 end of window (default: now).
            tenant_id: Optional tenant filter.
        """
        now = datetime.now(timezone.utc)
        period_end = to_time or now.isoformat()
        period_start = from_time or (now - timedelta(hours=24)).isoformat()

        def _collect(conn: sqlite3.Connection) -> AnalyticsSnapshot:
            where_clauses = [
                "timestamp >= ?",
                "timestamp <= ?",
            ]
            params: List[Any] = [period_start, period_end]

            if tenant_id:
                where_clauses.append("tenant_id = ?")
                params.append(tenant_id)

            where_sql = " AND ".join(where_clauses)

            # Total
            total_row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                f"SELECT COUNT(*) FROM _zenic_analytics_signals WHERE {where_sql}",
                params,
            ).fetchone()
            total = total_row[0] if total_row else 0

            # By category
            by_category: Dict[str, int] = {}
            for row in conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                f"SELECT category, COUNT(*) FROM _zenic_analytics_signals "
                f"WHERE {where_sql} GROUP BY category",
                params,
            ):
                by_category[row[0]] = row[1]

            # By severity
            by_severity: Dict[str, int] = {}
            for row in conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                f"SELECT severity, COUNT(*) FROM _zenic_analytics_signals "
                f"WHERE {where_sql} GROUP BY severity",
                params,
            ):
                by_severity[row[0]] = row[1]

            # By source
            by_source: Dict[str, int] = {}
            for row in conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                f"SELECT source, COUNT(*) FROM _zenic_analytics_signals "
                f"WHERE {where_sql} GROUP BY source ORDER BY COUNT(*) DESC LIMIT 20",
                params,
            ):
                by_source[row[0]] = row[1]

            # Rate per hour
            start_dt = datetime.fromisoformat(period_start)
            end_dt = datetime.fromisoformat(period_end)
            hours = max((end_dt - start_dt).total_seconds() / 3600, 0.01)
            rate = total / hours

            return AnalyticsSnapshot(
                total_exceptions=total,
                by_category=by_category,
                by_severity=by_severity,
                by_source=by_source,
                top_patterns=[],  # filled below
                period_start=period_start,
                period_end=period_end,
                exception_rate_per_hour=round(rate, 2),
            )

        snapshot = _retry_db(self._with_conn, _collect)

        # Add top patterns (uses detect_patterns which does its own DB access)
        try:
            patterns = self.detect_patterns(tenant_id=tenant_id)
            snapshot.top_patterns = sorted(
                patterns, key=lambda p: p.frequency, reverse=True,
            )[:10]
        except Exception as exc:
            logger.warning(
                "ExceptionAnalytics: error detecting patterns for snapshot: %s",
                exc,
            )

        return snapshot

    # ── Pattern detection ─────────────────────────────────

    def detect_patterns(
        self,
        tenant_id: str = "",
    ) -> List[ExceptionPattern]:
        """Detect recurring exception patterns.

        Groups signals by ``category + source``, then for each group:
          - Calculates frequency and average interval between occurrences
          - Determines trend by comparing recent frequency to older
          - Samples up to 5 messages
        """
        def _query(conn: sqlite3.Connection) -> List[ExceptionPattern]:
            params: List[Any] = []
            tenant_filter = ""
            if tenant_id:
                tenant_filter = "AND tenant_id = ?"
                params.append(tenant_id)

            # Group by category + source
            group_rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                f"""
                SELECT category, source, COUNT(*) as freq,
                       MIN(timestamp) as first_seen,
                       MAX(timestamp) as last_seen
                FROM _zenic_analytics_signals
                WHERE 1=1 {tenant_filter}
                GROUP BY category, source
                HAVING freq >= 2
                ORDER BY freq DESC
                """,
                params,
            ).fetchall()

            patterns: List[ExceptionPattern] = []
            now = datetime.now(timezone.utc)

            for row in group_rows:
                category_str, source, freq, first_seen, last_seen = row

                try:
                    category = ExceptionCategory(category_str)
                except ValueError:
                    category = ExceptionCategory.SYSTEM_ERROR

                # Average interval
                avg_interval = 0.0
                try:
                    first_dt = datetime.fromisoformat(first_seen)
                    last_dt = datetime.fromisoformat(last_seen)
                    span_seconds = (last_dt - first_dt).total_seconds()
                    if freq > 1 and span_seconds > 0:
                        avg_interval = span_seconds / (freq - 1)
                except (ValueError, TypeError):
                    pass

                # Trend: compare recent half vs older half
                trend = self._compute_trend(
                    conn, category_str, source, tenant_filter, params, now,
                )

                # Sample messages (up to 5)
                msg_rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    f"""
                    SELECT message FROM _zenic_analytics_signals
                    WHERE category = ? AND source = ? {tenant_filter}
                    ORDER BY timestamp DESC LIMIT 5
                    """,
                    [category_str, source] + params,
                ).fetchall()
                sample_messages = [r[0] for r in msg_rows]

                pattern = ExceptionPattern(
                    category=category,
                    source=source,
                    frequency=freq,
                    avg_interval_seconds=round(avg_interval, 2),
                    first_seen=first_seen,
                    last_seen=last_seen,
                    trend=trend,
                    sample_messages=sample_messages,
                )
                patterns.append(pattern)

            return patterns

        with self._lock:
            return _retry_db(self._with_conn, _query)

    def _compute_trend(
        self,
        conn: sqlite3.Connection,
        category: str,
        source: str,
        tenant_filter: str,
        params: List[Any],
        now: datetime,
    ) -> str:
        """Compare recent vs older frequency to determine trend."""
        try:
            mid_point = (now - timedelta(hours=12)).isoformat()
            recent_count = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                f"""
                SELECT COUNT(*) FROM _zenic_analytics_signals
                WHERE category = ? AND source = ?
                  AND timestamp >= ? {tenant_filter}
                """,
                [category, source, mid_point] + params,
            ).fetchone()[0]

            older_count = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                f"""
                SELECT COUNT(*) FROM _zenic_analytics_signals
                WHERE category = ? AND source = ?
                  AND timestamp < ? {tenant_filter}
                """,
                [category, source, mid_point] + params,
            ).fetchone()[0]

            if older_count == 0:
                return "increasing" if recent_count > 0 else "stable"
            ratio = recent_count / older_count
            if ratio > 1.5:
                return "increasing"
            if ratio < 0.5:
                return "decreasing"
            return "stable"
        except Exception:
            return "stable"

    # ── Trend ─────────────────────────────────────────────

    def get_trend(
        self,
        category: ExceptionCategory,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """Return daily exception counts for a category over *days*.

        Each dict has ``date`` and ``count`` keys.
        """
        def _query(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=days)
            ).isoformat()
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                SELECT DATE(timestamp) as day, COUNT(*) as cnt
                FROM _zenic_analytics_signals
                WHERE category = ? AND timestamp >= ?
                GROUP BY day
                ORDER BY day
                """,
                (category.value, cutoff),
            ).fetchall()
            return [{"date": r[0], "count": r[1]} for r in rows]

        return _retry_db(self._with_conn, _query)

    # ── Top sources ───────────────────────────────────────

    def get_top_sources(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return sources with the most exceptions."""
        def _query(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                SELECT source, COUNT(*) as cnt,
                       COUNT(DISTINCT category) as category_count
                FROM _zenic_analytics_signals
                GROUP BY source
                ORDER BY cnt DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [
                {
                    "source": r[0],
                    "count": r[1],
                    "category_count": r[2],
                }
                for r in rows
            ]

        return _retry_db(self._with_conn, _query)

    # ── Hourly distribution ───────────────────────────────

    def get_hourly_distribution(self) -> Dict[int, int]:
        """Return exception counts by hour of day (0-23)."""
        def _query(conn: sqlite3.Connection) -> Dict[int, int]:
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                SELECT CAST(STRFTIME('%H', timestamp) AS INTEGER) as hour,
                       COUNT(*) as cnt
                FROM _zenic_analytics_signals
                GROUP BY hour
                ORDER BY hour
                """
            ).fetchall()
            return {r[0]: r[1] for r in rows}

        return _retry_db(self._with_conn, _query)


# ── Singleton ─────────────────────────────────────────────────

