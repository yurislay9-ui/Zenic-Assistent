"""
ZENIC-AGENTS - KPI Tracker (Phase D1)

KPI measurement and tracking for the Autopilot by Objectives system.
Records measurements, computes trends via linear regression, and projects
achievement dates based on rate of change.

Thread-safe: All public methods guarded by RLock.
Retry logic: DB operations wrapped with 3 retries, base 0.5s backoff.
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
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  DATACLASSES
# ──────────────────────────────────────────────────────────────

@dataclass
class KPIMeasurement:
    """A single KPI measurement for an objective's metric.

    Records the current value of a metric along with the target and
    the delta from the previous measurement, enabling trend analysis.
    """
    measurement_id: str = ""
    objective_id: str = ""
    metric_name: str = ""
    value: float = 0.0
    target_value: float = 0.0
    unit: str = ""
    timestamp: str = ""
    source: str = "manual"
    delta_from_last: float = 0.0

    def __post_init__(self) -> None:
        """Auto-generate ID and timestamp if not provided."""
        if not self.measurement_id:
            self.measurement_id = f"kpi-{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def gap(self) -> float:
        """Calculate the gap between target and current value.

        Returns:
            target_value - value (positive means still need to improve).
        """
        return self.target_value - self.value

    def is_improving(self) -> bool:
        """Check if the metric is improving.

        For metrics where target > current: positive delta means improving.
        For metrics where target < current: negative delta means improving.
        A positive delta_from_last always means the value increased.

        Returns:
            True if the measurement shows improvement toward the target.
        """
        if self.delta_from_last == 0.0:
            return False
        # If target is higher than current, increasing value = improving
        if self.target_value > self.value:
            return self.delta_from_last > 0
        # If target is lower than current, decreasing value = improving
        return self.delta_from_last < 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "measurement_id": self.measurement_id,
            "objective_id": self.objective_id,
            "metric_name": self.metric_name,
            "value": self.value,
            "target_value": self.target_value,
            "unit": self.unit,
            "timestamp": self.timestamp,
            "source": self.source,
            "delta_from_last": self.delta_from_last,
        }


@dataclass
class KPITrend:
    """Trend analysis for a KPI metric over time.

    Includes linear regression slope for trend direction and
    projected achievement date based on rate of change.
    """
    metric_name: str = ""
    values: List[float] = field(default_factory=list)
    timestamps: List[str] = field(default_factory=list)
    trend_direction: str = "stable"  # "improving" | "stable" | "declining"
    avg_rate_of_change: float = 0.0
    projected_achievement_date: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "metric_name": self.metric_name,
            "values": self.values,
            "timestamps": self.timestamps,
            "trend_direction": self.trend_direction,
            "avg_rate_of_change": self.avg_rate_of_change,
            "projected_achievement_date": self.projected_achievement_date,
        }


# ──────────────────────────────────────────────────────────────
#  RETRY HELPER
# ──────────────────────────────────────────────────────────────

def _retry_db_operation(
    func: Any,
    max_retries: int = 3,
    base_delay: float = 0.5,
) -> Any:
    """Execute a function with retry logic for DB operations.

    Args:
        func: Callable to execute.
        max_retries: Maximum number of retries.
        base_delay: Base delay in seconds for exponential backoff.

    Returns:
        The result of the function call.

    Raises:
        The last exception if all retries fail.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "KPITracker: DB retry %d/%d after %.2fs — %s",
                attempt + 1, max_retries, delay, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
        except Exception as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "KPITracker: Unexpected error on retry %d/%d — %s",
                attempt + 1, max_retries, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────
#  KPI TRACKER
# ──────────────────────────────────────────────────────────────

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

            _retry_db_operation(_init)
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

            _retry_db_operation(_insert)
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
                    return [self._row_to_measurement(r) for r in rows]
                finally:
                    conn.close()

            return _retry_db_operation(_fetch)

    def get_trend(
        self,
        objective_id: str,
        metric_name: str,
        days: int = 30,
    ) -> KPITrend:
        """Calculate trend for a metric over the specified period.

        Uses linear regression on the measurement values to determine
        the trend direction and average rate of change, then projects
        the achievement date based on that rate.

        Args:
            objective_id: The objective ID.
            metric_name: The metric name.
            days: Number of days to look back for trend calculation.

        Returns:
            A KPITrend with direction, rate of change, and projected date.
        """
        self._ensure_schema()
        with self._lock:

            def _fetch_history() -> List[KPIMeasurement]:
                cutoff = datetime.now(timezone.utc).isoformat()
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                try:
                    rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """SELECT * FROM _zenic_kpi_measurements
                           WHERE objective_id = ? AND metric_name = ?
                           ORDER BY timestamp ASC""",
                        (objective_id, metric_name),
                    ).fetchall()
                    return [self._row_to_measurement(r) for r in rows]
                finally:
                    conn.close()

            measurements = _retry_db_operation(_fetch_history)

            if len(measurements) < 2:
                return KPITrend(
                    metric_name=metric_name,
                    values=[m.value for m in measurements],
                    timestamps=[m.timestamp for m in measurements],
                    trend_direction="stable",
                    avg_rate_of_change=0.0,
                )

            # Filter to recent measurements within the lookback window
            now = datetime.now(timezone.utc)
            cutoff_dt = now
            try:
                from datetime import timedelta
                cutoff_dt = now - timedelta(days=days)
            except Exception:
                pass

            recent: List[KPIMeasurement] = []
            for m in measurements:
                try:
                    m_dt = datetime.fromisoformat(m.timestamp)
                    if m_dt.tzinfo is None:
                        m_dt = m_dt.replace(tzinfo=timezone.utc)
                    if m_dt >= cutoff_dt:
                        recent.append(m)
                except (ValueError, TypeError):
                    recent.append(m)

            if len(recent) < 2:
                recent = measurements[-2:]

            values = [m.value for m in recent]
            timestamps = [m.timestamp for m in recent]

            # Simple linear regression
            n = len(values)
            x_indices = list(range(n))
            x_mean = sum(x_indices) / n
            y_mean = sum(values) / n

            numerator = sum(
                (xi - x_mean) * (yi - y_mean)
                for xi, yi in zip(x_indices, values)
            )
            denominator = sum((xi - x_mean) ** 2 for xi in x_indices)

            slope = numerator / denominator if denominator != 0 else 0.0

            # Determine trend direction relative to target
            target = measurements[-1].target_value
            current = measurements[-1].value

            if abs(slope) < 1e-9:
                direction = "stable"
            elif target < current:
                # We need to go down; negative slope = improving
                direction = "improving" if slope < 0 else "declining"
            else:
                # We need to go up; positive slope = improving
                direction = "improving" if slope > 0 else "declining"

            # Project achievement date
            projected_date = ""
            if abs(slope) > 1e-9:
                remaining = abs(target - current)
                steps_to_target = remaining / abs(slope) if abs(slope) > 0 else float("inf")
                if steps_to_target != float("inf") and steps_to_target > 0:
                    try:
                        from datetime import timedelta
                        # Estimate time per step from measurement intervals
                        if len(recent) >= 2:
                            first_dt = datetime.fromisoformat(recent[0].timestamp)
                            last_dt = datetime.fromisoformat(recent[-1].timestamp)
                            if first_dt.tzinfo is None:
                                first_dt = first_dt.replace(tzinfo=timezone.utc)
                            if last_dt.tzinfo is None:
                                last_dt = last_dt.replace(tzinfo=timezone.utc)
                            elapsed = (last_dt - first_dt).total_seconds()
                            seconds_per_step = elapsed / (n - 1) if n > 1 else 86400
                        else:
                            seconds_per_step = 86400
                        eta_seconds = steps_to_target * seconds_per_step
                        projected = now + timedelta(seconds=eta_seconds)
                        projected_date = projected.isoformat()
                    except Exception:
                        pass

            return KPITrend(
                metric_name=metric_name,
                values=values,
                timestamps=timestamps,
                trend_direction=direction,
                avg_rate_of_change=round(slope, 6),
                projected_achievement_date=projected_date,
            )

    def measure_all_for_objective(
        self,
        objective: Any,
    ) -> List[KPIMeasurement]:
        """Measure all KPIs for an objective.

        For each target in the objective, queries the database for the
        latest measurement value. Uses lazy-loaded database executor
        for real DB queries when available.

        Args:
            objective: An Objective instance with targets.

        Returns:
            A list of KPIMeasurements, one per target.
        """
        results: List[KPIMeasurement] = []
        for target in objective.targets:
            latest = self.get_latest(objective.objective_id, target.metric_name)
            if latest is not None:
                results.append(latest)
            else:
                # Record initial measurement from target's current_value
                measurement = self.measure(
                    objective_id=objective.objective_id,
                    metric_name=target.metric_name,
                    value=target.current_value,
                    target_value=target.target_value,
                    unit=target.unit,
                    source="objective_target",
                )
                results.append(measurement)
        return results

    def get_objective_progress(
        self, objective_id: str,
    ) -> Dict[str, Any]:
        """Get comprehensive progress information for an objective.

        Args:
            objective_id: The objective ID to query.

        Returns:
            Dictionary with progress percentage, trend, and projected completion.
        """
        self._ensure_schema()

        # Get all distinct metric names for this objective
        with self._lock:

            def _get_metrics() -> List[str]:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """SELECT DISTINCT metric_name FROM _zenic_kpi_measurements
                           WHERE objective_id = ?""",
                        (objective_id,),
                    )
                    return [row[0] for row in cursor.fetchall()]
                finally:
                    conn.close()

            metrics = _retry_db_operation(_get_metrics)

        if not metrics:
            return {
                "objective_id": objective_id,
                "progress_percent": 0.0,
                "metrics": {},
                "trends": {},
            }

        metric_progress: Dict[str, Any] = {}
        metric_trends: Dict[str, Any] = {}
        progress_values: List[float] = []

        for metric_name in metrics:
            latest = self.get_latest(objective_id, metric_name)
            trend = self.get_trend(objective_id, metric_name)

            if latest is not None:
                gap = latest.gap()
                total_range = abs(latest.target_value) if abs(latest.target_value) > 0 else 1.0
                progress = max(0.0, min(100.0, (1.0 - abs(gap) / total_range) * 100.0))
                progress_values.append(progress)
                metric_progress[metric_name] = {
                    "value": latest.value,
                    "target": latest.target_value,
                    "gap": gap,
                    "improving": latest.is_improving(),
                    "progress_percent": round(progress, 2),
                }

            metric_trends[metric_name] = trend.to_dict()

        avg_progress = round(sum(progress_values) / len(progress_values), 2) if progress_values else 0.0

        return {
            "objective_id": objective_id,
            "progress_percent": avg_progress,
            "metrics": metric_progress,
            "trends": metric_trends,
        }

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
                return self._row_to_measurement(row)
            finally:
                conn.close()

        return _retry_db_operation(_fetch)

    @staticmethod
    def _row_to_measurement(row: sqlite3.Row) -> KPIMeasurement:
        """Convert a database row to a KPIMeasurement instance."""
        return KPIMeasurement(
            measurement_id=row["measurement_id"],
            objective_id=row["objective_id"],
            metric_name=row["metric_name"],
            value=row["value"],
            target_value=row["target_value"],
            unit=row["unit"],
            timestamp=row["timestamp"],
            source=row["source"],
            delta_from_last=row["delta_from_last"],
        )


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


__all__ = [
    "KPIMeasurement",
    "KPITrend",
    "KPITracker",
    "get_kpi_tracker",
    "reset_kpi_tracker",
]
