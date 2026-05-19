"""
ZENIC-AGENTS — KPI Tracker: Trend Analysis

Contains the get_trend(), measure_all_for_objective(), and
get_objective_progress() methods, extracted from KPITracker to
keep the main module under 400 lines.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ._helpers import retry_db_operation, row_to_measurement
from ._types import KPIMeasurement, KPITrend

logger = logging.getLogger(__name__)


def get_trend(
    db_path: str,
    objective_id: str,
    metric_name: str,
    days: int = 30,
) -> KPITrend:
    """Calculate trend for a metric over the specified period.

    Uses linear regression on the measurement values to determine
    the trend direction and average rate of change, then projects
    the achievement date based on that rate.

    Args:
        db_path: Path to the SQLite database.
        objective_id: The objective ID.
        metric_name: The metric name.
        days: Number of days to look back for trend calculation.

    Returns:
        A KPITrend with direction, rate of change, and projected date.
    """
    def _fetch_history() -> List[KPIMeasurement]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """SELECT * FROM _zenic_kpi_measurements
                   WHERE objective_id = ? AND metric_name = ?
                   ORDER BY timestamp ASC""",
                (objective_id, metric_name),
            ).fetchall()
            return [row_to_measurement(r) for r in rows]
        finally:
            conn.close()

    measurements = retry_db_operation(_fetch_history)

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
    objective: Any,
    tracker_measure,       # KPITracker.measure
    tracker_get_latest,    # KPITracker.get_latest
) -> List[KPIMeasurement]:
    """Measure all KPIs for an objective.

    For each target in the objective, queries the database for the
    latest measurement value. Uses lazy-loaded database executor
    for real DB queries when available.

    Args:
        objective: An Objective instance with targets.
        tracker_measure: Bound method reference to KPITracker.measure.
        tracker_get_latest: Bound method reference to KPITracker.get_latest.

    Returns:
        A list of KPIMeasurements, one per target.
    """
    results: List[KPIMeasurement] = []
    for target in objective.targets:
        latest = tracker_get_latest(objective.objective_id, target.metric_name)
        if latest is not None:
            results.append(latest)
        else:
            # Record initial measurement from target's current_value
            measurement = tracker_measure(
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
    db_path: str,
    objective_id: str,
    tracker_get_latest,    # KPITracker.get_latest
    tracker_get_trend,     # KPITracker.get_trend
) -> Dict[str, Any]:
    """Get comprehensive progress information for an objective.

    Args:
        db_path: Path to the SQLite database.
        objective_id: The objective ID to query.
        tracker_get_latest: Bound method reference to KPITracker.get_latest.
        tracker_get_trend: Bound method reference to KPITracker.get_trend.

    Returns:
        Dictionary with progress percentage, trend, and projected completion.
    """
    # Get all distinct metric names for this objective
    def _get_metrics() -> List[str]:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """SELECT DISTINCT metric_name FROM _zenic_kpi_measurements
                   WHERE objective_id = ?""",
                (objective_id,),
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    metrics = retry_db_operation(_get_metrics)

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
        latest = tracker_get_latest(objective_id, metric_name)
        trend = tracker_get_trend(objective_id, metric_name)

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
