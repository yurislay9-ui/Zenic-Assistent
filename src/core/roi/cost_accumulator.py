"""
Zenic-Agents ROI — Cost Accumulator

Tracks cost per action across LLM tokens, API calls, compute time,
human time, storage, and network usage. Persists entries in SQLite
with thread-safe access, retry logic, and graceful degradation.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)

__all__ = [
    "CostCategory",
    "CostEntry",
    "CostAccumulator",
    "DEFAULT_UNIT_COSTS",
    "get_cost_accumulator",
    "reset_cost_accumulator",
]


# ── Enums ────────────────────────────────────────────────


class CostCategory(str, Enum):
    """Categories of operational cost."""

    LLM_TOKENS = "llm_tokens"
    API_CALLS = "api_calls"
    COMPUTE_TIME = "compute_time"
    HUMAN_TIME = "human_time"
    STORAGE = "storage"
    NETWORK = "network"


# ── Default unit costs (USD) ─────────────────────────────


DEFAULT_UNIT_COSTS: Dict[CostCategory, float] = {
    CostCategory.LLM_TOKENS: 0.00003,
    CostCategory.API_CALLS: 0.001,
    CostCategory.COMPUTE_TIME: 0.05,
    CostCategory.HUMAN_TIME: 25.0,
    CostCategory.STORAGE: 0.023,
    CostCategory.NETWORK: 0.09,
}


# ── Data model ──────────────────────────────────────────


@dataclass
class CostEntry:
    """A single recorded cost entry."""

    entry_id: str = ""
    action_id: str = ""
    category: CostCategory = CostCategory.LLM_TOKENS
    quantity: float = 0.0
    unit_cost: float = 0.0
    total_cost: float = 0.0
    currency: str = "USD"
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.entry_id:
            self.entry_id = uuid.uuid4().hex[:16]
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if self.total_cost == 0.0 and (self.quantity != 0.0 or self.unit_cost != 0.0):
            self.total_cost = round(self.quantity * self.unit_cost, 6)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "entry_id": self.entry_id,
            "action_id": self.action_id,
            "category": self.category.value,
            "quantity": self.quantity,
            "unit_cost": self.unit_cost,
            "total_cost": self.total_cost,
            "currency": self.currency,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


# ── Retry helper ─────────────────────────────────────────

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.1  # seconds


def _with_retry(fn, label: str = "CostAccumulator DB op"):
    """Execute *fn* with exponential-backoff retry (3 attempts)."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.debug(
                    "%s error (attempt %d/%d): %s — retrying in %.2fs",
                    label, attempt, _MAX_RETRIES, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "%s failed after %d attempts: %s", label, _MAX_RETRIES, exc,
                )
    # All retries exhausted — re-raise
    if last_exc is not None:
        raise last_exc  # type: ignore[misc]


# ── CostAccumulator ──────────────────────────────────────


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

    # ── Schema ──────────────────────────────────────────

    def _init_db(self) -> None:
        """Create the _zenic_costs table if it does not exist."""
        try:
            def _create() -> None:
                conn = sqlite3.connect(self._db_path)
                conn.execute("""
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
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_costs_action "
                    "ON _zenic_costs(action_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_costs_timestamp "
                    "ON _zenic_costs(timestamp)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_costs_category "
                    "ON _zenic_costs(category)"
                )
                conn.commit()
                conn.close()

            _with_retry(_create, label="CostAccumulator init_db")
        except Exception as exc:
            logger.error("CostAccumulator: DB init failed: %s", exc)

    # ── Recording ───────────────────────────────────────

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
        """Convenience method to record all cost categories for an action at once.

        Only non-zero categories are recorded.
        """
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

    # ── Queries ─────────────────────────────────────────

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
                    row = conn.execute(sql, params).fetchone()
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
                    rows = conn.execute(sql, params).fetchall()
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
                    rows = conn.execute(
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
                    total = conn.execute(
                        "SELECT COALESCE(SUM(total_cost), 0) FROM _zenic_costs"
                    ).fetchone()[0]
                    count = conn.execute(
                        "SELECT COUNT(*) FROM _zenic_costs"
                    ).fetchone()[0]
                    by_cat = conn.execute(
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

    # ── Persistence ─────────────────────────────────────

    def _persist_entry(self, entry: CostEntry, tenant_id: str = "") -> None:
        """Insert a CostEntry row with retry."""

        def _insert() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
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


# ── Singleton ────────────────────────────────────────────

_cost_accumulator: Optional[CostAccumulator] = None
_lock = threading.Lock()


def get_cost_accumulator(**kwargs: Any) -> CostAccumulator:
    """Get or create the global CostAccumulator singleton."""
    global _cost_accumulator
    with _lock:
        if _cost_accumulator is None:
            _cost_accumulator = CostAccumulator(**kwargs)
        return _cost_accumulator


def reset_cost_accumulator() -> None:
    """Reset the global CostAccumulator (for testing)."""
    global _cost_accumulator
    _cost_accumulator = None
