"""
Value Tracker — ValueTracker class.

Thread-safe value tracker with SQLite persistence.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from ._types import ValueCategory, ValueEntry, DEFAULT_UNIT_VALUES, _with_retry

logger = logging.getLogger(__name__)


class ValueTracker:
    """Thread-safe value tracker with SQLite persistence.

    Records value entries (hours saved, errors avoided, etc.) and
    provides aggregate queries including ROI computation.

    Usage::

        vt = ValueTracker()
        entry = vt.record_value(ValueCategory.HOURS_SAVED, 5.0)
        roi = vt.get_roi()
    """

    def __init__(self, db_path: str = "roi_value.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        """Create the _zenic_values table if it does not exist."""
        try:
            def _create() -> None:
                conn = sqlite3.connect(self._db_path)
                conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                    CREATE TABLE IF NOT EXISTS _zenic_values (
                        entry_id TEXT PRIMARY KEY,
                        category TEXT NOT NULL,
                        action_id TEXT NOT NULL DEFAULT '',
                        quantity REAL NOT NULL DEFAULT 0,
                        unit_value REAL NOT NULL DEFAULT 0,
                        total_value REAL NOT NULL DEFAULT 0,
                        currency TEXT NOT NULL DEFAULT 'USD',
                        timestamp TEXT NOT NULL DEFAULT '',
                        tenant_id TEXT NOT NULL DEFAULT '',
                        metadata TEXT NOT NULL DEFAULT '{}'
                    )
                """)
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_values_category "
                    "ON _zenic_values(category)"
                )
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_values_timestamp "
                    "ON _zenic_values(timestamp)"
                )
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_values_tenant "
                    "ON _zenic_values(tenant_id)"
                )
                conn.commit()
                conn.close()

            _with_retry(_create, label="ValueTracker init_db")
        except Exception as exc:
            logger.error("ValueTracker: DB init failed: %s", exc)

    def record_value(
        self,
        category: ValueCategory,
        quantity: float,
        unit_value: float = 0.0,
        action_id: str = "",
        tenant_id: str = "",
        currency: str = "USD",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ValueEntry:
        """Record a single value entry.

        If *unit_value* is 0, the default unit value for *category* is used.
        """
        if unit_value == 0.0:
            unit_value = DEFAULT_UNIT_VALUES.get(category, 0.0)

        entry = ValueEntry(
            category=category,
            action_id=action_id,
            quantity=quantity,
            unit_value=unit_value,
            currency=currency,
            tenant_id=tenant_id,
            metadata=metadata or {},
        )

        with self._lock:
            self._persist_entry(entry)

        logger.debug(
            "ValueTracker: recorded %s value: qty=%.4f unit=%.6f total=%.6f",
            category.value, quantity, unit_value, entry.total_value,
        )
        return entry

    def record_automation_value(
        self,
        hours_saved: float = 0,
        errors_avoided: int = 0,
        revenue_recovered: float = 0,
        tasks_automated: int = 0,
        action_id: str = "",
        tenant_id: str = "",
    ) -> List[ValueEntry]:
        """Convenience method to record multiple value categories at once."""
        entries: List[ValueEntry] = []
        with self._lock:
            if hours_saved > 0:
                entries.append(
                    self.record_value(
                        ValueCategory.HOURS_SAVED,
                        hours_saved,
                        action_id=action_id,
                        tenant_id=tenant_id,
                    )
                )
            if errors_avoided > 0:
                entries.append(
                    self.record_value(
                        ValueCategory.ERRORS_AVOIDED,
                        float(errors_avoided),
                        action_id=action_id,
                        tenant_id=tenant_id,
                    )
                )
            if revenue_recovered > 0:
                entries.append(
                    self.record_value(
                        ValueCategory.REVENUE_RECOVERED,
                        revenue_recovered,
                        action_id=action_id,
                        tenant_id=tenant_id,
                    )
                )
            if tasks_automated > 0:
                entries.append(
                    self.record_value(
                        ValueCategory.TASKS_AUTOMATED,
                        float(tasks_automated),
                        action_id=action_id,
                        tenant_id=tenant_id,
                    )
                )
        return entries

    def get_total_value(
        self,
        from_time: str = "",
        to_time: str = "",
        category: Optional[ValueCategory] = None,
        tenant_id: str = "",
    ) -> float:
        """Return total value with optional time-range, category, and tenant filters."""
        with self._lock:
            try:
                def _query() -> float:
                    conn = sqlite3.connect(self._db_path)
                    sql = "SELECT COALESCE(SUM(total_value), 0) FROM _zenic_values WHERE 1=1"
                    params: list = []
                    if from_time:
                        sql += " AND timestamp >= ?"
                        params.append(from_time)
                    if to_time:
                        sql += " AND timestamp <= ?"
                        params.append(to_time)
                    if category is not None:
                        sql += " AND category = ?"
                        params.append(category.value)
                    if tenant_id:
                        sql += " AND tenant_id = ?"
                        params.append(tenant_id)
                    row = conn.execute(sql, params).fetchone()  # nosemgrep: sqlalchemy-execute-raw-query
                    conn.close()
                    return float(row[0]) if row else 0.0

                return _with_retry(_query, label="ValueTracker get_total_value")
            except Exception as exc:
                logger.error("ValueTracker: get_total_value failed: %s", exc)
                return 0.0

    def get_value_breakdown(
        self,
        from_time: str = "",
        to_time: str = "",
        tenant_id: str = "",
    ) -> Dict[str, float]:
        """Return value grouped by category."""
        with self._lock:
            try:
                def _query() -> Dict[str, float]:
                    conn = sqlite3.connect(self._db_path)
                    sql = (
                        "SELECT category, COALESCE(SUM(total_value), 0) "
                        "FROM _zenic_values WHERE 1=1"
                    )
                    params: list = []
                    if from_time:
                        sql += " AND timestamp >= ?"
                        params.append(from_time)
                    if to_time:
                        sql += " AND timestamp <= ?"
                        params.append(to_time)
                    if tenant_id:
                        sql += " AND tenant_id = ?"
                        params.append(tenant_id)
                    sql += " GROUP BY category"
                    rows = conn.execute(sql, params).fetchall()  # nosemgrep: sqlalchemy-execute-raw-query
                    conn.close()
                    return {row[0]: float(row[1]) for row in rows}

                return _with_retry(_query, label="ValueTracker get_value_breakdown")
            except Exception as exc:
                logger.error("ValueTracker: get_value_breakdown failed: %s", exc)
                return {}

    def get_daily_value(self, days: int = 30) -> List[Dict[str, Any]]:
        """Return daily value totals for the last *days* days."""
        with self._lock:
            try:
                def _query() -> List[Dict[str, Any]]:
                    conn = sqlite3.connect(self._db_path)
                    cutoff = time.strftime(
                        "%Y-%m-%dT00:00:00Z",
                        time.gmtime(time.time() - days * 86400),
                    )
                    rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT substr(timestamp,1,10) AS day, "
                        "COALESCE(SUM(total_value), 0) "
                        "FROM _zenic_values WHERE timestamp >= ? "
                        "GROUP BY day ORDER BY day",
                        (cutoff,),
                    ).fetchall()
                    conn.close()
                    return [{"date": row[0], "value": float(row[1])} for row in rows]

                return _with_retry(_query, label="ValueTracker get_daily_value")
            except Exception as exc:
                logger.error("ValueTracker: get_daily_value failed: %s", exc)
                return []

    def get_roi(
        self,
        from_time: str = "",
        to_time: str = "",
        tenant_id: str = "",
    ) -> Dict[str, float]:
        """Compute ROI: total_value, total_cost, roi_percent, net_value."""
        total_value = self.get_total_value(
            from_time=from_time, to_time=to_time, tenant_id=tenant_id,
        )
        total_cost: float = 0.0
        try:
            from ..cost_accumulator import get_cost_accumulator
            acc = get_cost_accumulator()
            total_cost = acc.get_total_cost(
                from_time=from_time, to_time=to_time, tenant_id=tenant_id,
            )
        except Exception as exc:
            logger.debug("ValueTracker: CostAccumulator unavailable for ROI: %s", exc)

        roi_percent = 0.0
        if total_cost > 0:
            roi_percent = round(((total_value - total_cost) / total_cost) * 100, 2)

        return {
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "roi_percent": roi_percent,
            "net_value": round(total_value - total_cost, 2),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return summary statistics."""
        with self._lock:
            try:
                def _query() -> Dict[str, Any]:
                    conn = sqlite3.connect(self._db_path)
                    total = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT COALESCE(SUM(total_value), 0) FROM _zenic_values"
                    ).fetchone()[0]
                    count = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT COUNT(*) FROM _zenic_values"
                    ).fetchone()[0]
                    by_cat = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT category, COALESCE(SUM(total_value), 0), COUNT(*) "
                        "FROM _zenic_values GROUP BY category"
                    ).fetchall()
                    conn.close()

                    breakdown: Dict[str, Any] = {}
                    for cat, val, cnt in by_cat:
                        breakdown[cat] = {"total_value": float(val), "count": int(cnt)}

                    return {
                        "total_value": float(total),
                        "entry_count": int(count),
                        "breakdown": breakdown,
                    }

                return _with_retry(_query, label="ValueTracker get_stats")
            except Exception as exc:
                logger.error("ValueTracker: get_stats failed: %s", exc)
                return {"total_value": 0.0, "entry_count": 0, "breakdown": {}}

    def _persist_entry(self, entry: ValueEntry) -> None:
        """Insert a ValueEntry row with retry."""

        def _insert() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT INTO _zenic_values
                   (entry_id, category, action_id, quantity, unit_value,
                    total_value, currency, timestamp, tenant_id, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.entry_id,
                    entry.category.value,
                    entry.action_id,
                    entry.quantity,
                    entry.unit_value,
                    entry.total_value,
                    entry.currency,
                    entry.timestamp,
                    entry.tenant_id,
                    json.dumps(entry.metadata),
                ),
            )
            conn.commit()
            conn.close()

        try:
            _with_retry(_insert, label="ValueTracker persist_entry")
        except Exception as exc:
            logger.error("ValueTracker: persist failed: %s", exc)
