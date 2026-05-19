"""
ZENIC-AGENTS - KPI Tracker (Phase D1)

KPI measurement and tracking for the Autopilot by Objectives system.
Records measurements, computes trends via linear regression, and projects
achievement dates based on rate of change.

Thread-safe: All public methods guarded by RLock.
Retry logic: DB operations wrapped with 3 retries, base 0.5s backoff.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ._helpers import retry_db_operation, row_to_measurement
from ._trend_analysis import (
    get_objective_progress as _get_objective_progress,
    get_trend as _get_trend,
    measure_all_for_objective as _measure_all_for_objective,
)
from ._types import KPIMeasurement, KPITrend

logger = logging.getLogger(__name__)

__all__ = [
    "KPIMeasurement",
    "KPITrend",
    "KPITracker",
    "get_kpi_tracker",
    "reset_kpi_tracker",
]


class KPITracker:
    """KPI measurement and trend analysis for autopilot objectives.

    Records measurements, computes trends via linear regression,
    and projects achievement dates based on rate of change.

    Thread-safe: All public methods guarded by RLock.
    """

    def __init__(self, db_path: str = "kpi_tracker.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._initialized = False

    def _ensure_schema(self) -> None:
        """Create the KPI measurements table if it does not exist."""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return

            def _init() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE TABLE IF NOT EXISTS _zenic_kpi_measurements (
                            measurement_id TEXT PRIMARY KEY,
                            objective_id TEXT NOT NULL,
                            metric_name TEXT NOT NULL,
                            value REAL NOT NULL,
                            target_value REAL NOT NULL,
                            unit TEXT NOT NULL DEFAULT '',
                            timestamp TEXT NOT NULL,
                            source TEXT NOT NULL DEFAULT 'manual',
                            delta_from_last REAL NOT NULL DEFAULT 0.0
                        )
                    """)
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE INDEX IF NOT EXISTS idx_zenic_kpi_obj_metric
                        ON _zenic_kpi_measurements(objective_id, metric_name)
                    """)
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE INDEX IF NOT EXISTS idx_zenic_kpi_timestamp
                        ON _zenic_kpi_measurements(timestamp)
                    """)
                    conn.commit()
                finally:
                    conn.close()

            retry_db_operation(_init)
            self._initialized = True
            logger.info("KPITracker: Schema initialized at %s", self._db_path)

    # ── Core Measurement ───────────────────────────────────

    def measure(
        self,
        objective_id: str,
        metric_name: str,
        value: float,
        target_value: float,
        unit: str = "",
        source: str = "manual",
    ) -> KPIMeasurement:
        """Record a new KPI measurement.

        Calculates delta from the last measurement for the same
        objective + metric, enabling trend analysis.

        Args:
            objective_id: The objective this measurement belongs to.
            metric_name: Name of the metric being measured.
            value: Current measured value.
            target_value: Target value for this metric.
            unit: Unit of measurement (e.g. "%", "USD", "count").
            source: Source of the measurement (e.g. "manual", "database", "api").

        Returns:
            The persisted KPIMeasurement with delta calculated.
        """
        self._ensure_schema()
        with self._lock:
            # Get last measurement to calculate delta
            last = self._get_last_internal(objective_id, metric_name)
            delta = 0.0
            if last is not None:
                delta = value - last.value

            measurement = KPIMeasurement(
                objective_id=objective_id,
                metric_name=metric_name,
                value=value,
                target_value=target_value,
                unit=unit,
                source=source,
                delta_from_last=delta,
            )

            data = measurement.to_dict()

            def _insert() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """INSERT INTO _zenic_kpi_measurements
                           (measurement_id, objective_id, metric_name, value,
                            target_value, unit, timestamp, source, delta_from_last)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (
                            data["measurement_id"],
                            data["objective_id"],
                            data["metric_name"],
                            data["value"],
                            data["target_value"],
                            data["unit"],
                            data["timestamp"],
                            data["source"],
                            data["delta_from_last"],
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

            retry_db_operation(_insert)
            logger.info(
                "KPITracker: Measured %s=%s (target=%s, delta=%.4f) for %s",
                metric_name, value, target_value, delta, objective_id,
            )
            return measurement

    def get_latest(
        self, objective_id: str, metric_name: str,
    ) -> Optional[KPIMeasurement]:
        """Get the latest measurement for a metric.

        Args:
            objective_id: The objective ID.
            metric_name: The metric name.

        Returns:
            The latest KPIMeasurement, or None if no measurements exist.
        """
        self._ensure_schema()
        with self._lock:
            return self._get_last_internal(objective_id, metric_name)

    def get_history(
        self,
        objective_id: str,
        metric_name: str,
        limit: int = 100,
    ) -> List[KPIMeasurement]:
        """Get measurement history for a metric.

        Args:
            objective_id: The objective ID.
            metric_name: The metric name.
            limit: Maximum number of measurements to return.

        Returns:
            A list of KPIMeasurements, newest first.
        """
        self._ensure_schema()
        with self._lock:

            def _fetch() -> List[KPIMeasurement]:
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                try:
                    rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """SELECT * FROM _zenic_kpi_measurements
                           WHERE objective_id = ? AND metric_name = ?
                           ORDER BY timestamp DESC LIMIT ?""",
                        (objective_id, metric_name, limit),
                    ).fetchall()
                    return [row_to_measurement(r) for r in rows]
                finally:
                    conn.close()

            return retry_db_operation(_fetch)

    def get_trend(
        self,
        objective_id: str,
        metric_name: str,
        days: int = 30,
    ) -> KPITrend:
        """Calculate trend for a metric over the specified period.

        Delegates to the standalone _get_trend function.

        Args:
            objective_id: The objective ID.
            metric_name: The metric name.
            days: Number of days to look back for trend calculation.

        Returns:
            A KPITrend with direction, rate of change, and projected date.
        """
        self._ensure_schema()
        return _get_trend(self._db_path, objective_id, metric_name, days)

    def measure_all_for_objective(
        self,
        objective: Any,
    ) -> List[KPIMeasurement]:
        """Measure all KPIs for an objective.

        Delegates to the standalone _measure_all_for_objective function.

        Args:
            objective: An Objective instance with targets.

        Returns:
            A list of KPIMeasurements, one per target.
        """
        return _measure_all_for_objective(
            objective, self.measure, self.get_latest,
        )

    def get_objective_progress(
        self, objective_id: str,
    ) -> Dict[str, Any]:
        """Get comprehensive progress information for an objective.

        Delegates to the standalone _get_objective_progress function.

        Args:
            objective_id: The objective ID to query.

        Returns:
            Dictionary with progress percentage, trend, and projected completion.
        """
        self._ensure_schema()
        return _get_objective_progress(
            self._db_path, objective_id, self.get_latest, self.get_trend,
        )

    # ── Internal Helpers ────────────────────────────────────

    def _get_last_internal(
        self, objective_id: str, metric_name: str,
    ) -> Optional[KPIMeasurement]:
        """Get the latest measurement without acquiring the lock.

        Caller must hold self._lock.
        """
        def _fetch() -> Optional[KPIMeasurement]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """SELECT * FROM _zenic_kpi_measurements
                       WHERE objective_id = ? AND metric_name = ?
                       ORDER BY timestamp DESC LIMIT 1""",
                    (objective_id, metric_name),
                ).fetchone()
                if row is None:
                    return None
                return row_to_measurement(row)
            finally:
                conn.close()

        return retry_db_operation(_fetch)


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_kpi_tracker_instance: Optional[KPITracker] = None
_kpi_tracker_lock = threading.Lock()


def get_kpi_tracker(db_path: str = "kpi_tracker.sqlite") -> KPITracker:
    """Get or create the global KPITracker instance.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        The singleton KPITracker instance.
    """
    global _kpi_tracker_instance
    with _kpi_tracker_lock:
        if _kpi_tracker_instance is None:
            _kpi_tracker_instance = KPITracker(db_path=db_path)
        return _kpi_tracker_instance


def reset_kpi_tracker() -> None:
    """Reset the global KPITracker instance (for testing)."""
    global _kpi_tracker_instance
    with _kpi_tracker_lock:
        _kpi_tracker_instance = None
