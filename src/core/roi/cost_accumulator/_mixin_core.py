"""
Cost Accumulator — CostAccumulator class.

Thread-safe cost accumulator with SQLite persistence.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from ._types import CostCategory, CostEntry, DEFAULT_UNIT_COSTS, _with_retry

logger = logging.getLogger(__name__)


class CostAccumulator:
    """Thread-safe cost accumulator with SQLite persistence.

    Records cost entries per action and provides aggregate queries
    for dashboards and reporting.

    Usage::

        acc = CostAccumulator()
        entry = acc.record_cost("action-1", CostCategory.LLM_TOKENS, 1500)
        total = acc.get_total_cost()
    """

    def __init__(self, db_path: str = "roi_costs.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        """Create the _zenic_costs table if it does not exist."""
        try:
            def _create() -> None:
                conn = sqlite3.connect(self._db_path)
                conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                    CREATE TABLE IF NOT EXISTS _zenic_costs (
                        entry_id TEXT PRIMARY KEY,
                        action_id TEXT NOT NULL DEFAULT '',
                        category TEXT NOT NULL,
                        quantity REAL NOT NULL DEFAULT 0,
                        unit_cost REAL NOT NULL DEFAULT 0,
                        total_cost REAL NOT NULL DEFAULT 0,
                        currency TEXT NOT NULL DEFAULT 'USD',
                        timestamp TEXT NOT NULL DEFAULT '',
                        tenant_id TEXT NOT NULL DEFAULT '',
                        metadata TEXT NOT NULL DEFAULT '{}'
                    )
                """)
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_costs_action "
                    "ON _zenic_costs(action_id)"
                )
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_costs_timestamp "
                    "ON _zenic_costs(timestamp)"
                )
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_costs_category "
                    "ON _zenic_costs(category)"
                )
                conn.commit()
                conn.close()

            _with_retry(_create, label="CostAccumulator init_db")
        except Exception as exc:
            logger.error("CostAccumulator: DB init failed: %s", exc)

    def record_cost(
        self,
        action_id: str,
        category: CostCategory,
        quantity: float,
        unit_cost: float = 0.0,
        currency: str = "USD",
        metadata: Optional[Dict[str, Any]] = None,
        tenant_id: str = "",
    ) -> CostEntry:
        """Record a single cost entry.

        If *unit_cost* is 0, the default unit cost for *category* is used.
        """
        if unit_cost == 0.0:
            unit_cost = DEFAULT_UNIT_COSTS.get(category, 0.0)

        entry = CostEntry(
            action_id=action_id,
            category=category,
            quantity=quantity,
            unit_cost=unit_cost,
            currency=currency,
            metadata=metadata or {},
        )

        with self._lock:
            self._persist_entry(entry, tenant_id=tenant_id)

        logger.debug(
            "CostAccumulator: recorded %s cost for '%s': qty=%.4f unit=%.6f total=%.6f",
            category.value, action_id, quantity, unit_cost, entry.total_cost,
        )
        return entry

    def record_action_cost(
        self,
        action_id: str,
        llm_tokens: int = 0,
        api_calls: int = 0,
        compute_seconds: float = 0.0,
        human_minutes: float = 0.0,
        storage_mb: float = 0.0,
        network_mb: float = 0.0,
        tenant_id: str = "",
    ) -> List[CostEntry]:
        """Convenience method to record all cost categories for an action at once."""
        entries: List[CostEntry] = []
        with self._lock:
            if llm_tokens > 0:
                entries.append(
                    self.record_cost(
                        action_id, CostCategory.LLM_TOKENS,
                        float(llm_tokens), tenant_id=tenant_id,
                    )
                )
            if api_calls > 0:
                entries.append(
                    self.record_cost(
                        action_id, CostCategory.API_CALLS,
                        float(api_calls), tenant_id=tenant_id,
                    )
                )
            if compute_seconds > 0.0:
                entries.append(
                    self.record_cost(
                        action_id, CostCategory.COMPUTE_TIME,
                        compute_seconds, tenant_id=tenant_id,
                    )
                )
            if human_minutes > 0.0:
                entries.append(
                    self.record_cost(
                        action_id, CostCategory.HUMAN_TIME,
                        human_minutes, tenant_id=tenant_id,
                    )
                )
            if storage_mb > 0.0:
                entries.append(
                    self.record_cost(
                        action_id, CostCategory.STORAGE,
                        storage_mb, tenant_id=tenant_id,
                    )
                )
            if network_mb > 0.0:
                entries.append(
                    self.record_cost(
                        action_id, CostCategory.NETWORK,
                        network_mb, tenant_id=tenant_id,
                    )
                )
        return entries

    def get_total_cost(
        self,
        from_time: str = "",
        to_time: str = "",
        category: Optional[CostCategory] = None,
        tenant_id: str = "",
    ) -> float:
        """Return total cost with optional time-range, category, and tenant filters."""
        with self._lock:
            try:
                def _query() -> float:
                    conn = sqlite3.connect(self._db_path)
                    sql = "SELECT COALESCE(SUM(total_cost), 0) FROM _zenic_costs WHERE 1=1"
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

                return _with_retry(_query, label="CostAccumulator get_total_cost")
            except Exception as exc:
                logger.error("CostAccumulator: get_total_cost failed: %s", exc)
                return 0.0

    def get_cost_breakdown(
        self,
        from_time: str = "",
        to_time: str = "",
        tenant_id: str = "",
    ) -> Dict[str, float]:
        """Return cost grouped by category."""
        with self._lock:
            try:
                def _query() -> Dict[str, float]:
                    conn = sqlite3.connect(self._db_path)
                    sql = (
                        "SELECT category, COALESCE(SUM(total_cost), 0) "
                        "FROM _zenic_costs WHERE 1=1"
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

                return _with_retry(_query, label="CostAccumulator get_cost_breakdown")
            except Exception as exc:
                logger.error("CostAccumulator: get_cost_breakdown failed: %s", exc)
                return {}

    def get_daily_costs(self, days: int = 30) -> List[Dict[str, Any]]:
        """Return daily cost totals for the last *days* days."""
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
                        "COALESCE(SUM(total_cost), 0) "
                        "FROM _zenic_costs WHERE timestamp >= ? "
                        "GROUP BY day ORDER BY day",
                        (cutoff,),
                    ).fetchall()
                    conn.close()
                    return [{"date": row[0], "cost": float(row[1])} for row in rows]

                return _with_retry(_query, label="CostAccumulator get_daily_costs")
            except Exception as exc:
                logger.error("CostAccumulator: get_daily_costs failed: %s", exc)
                return []

    def get_stats(self) -> Dict[str, Any]:
        """Return summary statistics."""
        with self._lock:
            try:
                def _query() -> Dict[str, Any]:
                    conn = sqlite3.connect(self._db_path)
                    total = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT COALESCE(SUM(total_cost), 0) FROM _zenic_costs"
                    ).fetchone()[0]
                    count = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT COUNT(*) FROM _zenic_costs"
                    ).fetchone()[0]
                    by_cat = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT category, COALESCE(SUM(total_cost), 0), COUNT(*) "
                        "FROM _zenic_costs GROUP BY category"
                    ).fetchall()
                    conn.close()

                    breakdown: Dict[str, Any] = {}
                    for cat, cost, cnt in by_cat:
                        breakdown[cat] = {"total_cost": float(cost), "count": int(cnt)}

                    return {
                        "total_cost": float(total),
                        "entry_count": int(count),
                        "breakdown": breakdown,
                    }

                return _with_retry(_query, label="CostAccumulator get_stats")
            except Exception as exc:
                logger.error("CostAccumulator: get_stats failed: %s", exc)
                return {"total_cost": 0.0, "entry_count": 0, "breakdown": {}}

    def _persist_entry(self, entry: CostEntry, tenant_id: str = "") -> None:
        """Insert a CostEntry row with retry."""

        def _insert() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT INTO _zenic_costs
                   (entry_id, action_id, category, quantity, unit_cost,
                    total_cost, currency, timestamp, tenant_id, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.entry_id,
                    entry.action_id,
                    entry.category.value,
                    entry.quantity,
                    entry.unit_cost,
                    entry.total_cost,
                    entry.currency,
                    entry.timestamp,
                    tenant_id,
                    json.dumps(entry.metadata),
                ),
            )
            conn.commit()
            conn.close()

        try:
            _with_retry(_insert, label="CostAccumulator persist_entry")
        except Exception as exc:
            logger.error("CostAccumulator: persist failed: %s", exc)
