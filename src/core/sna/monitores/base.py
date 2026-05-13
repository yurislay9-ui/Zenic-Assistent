"""
Zenic-Agents Asistente - SNA Monitor Base

Abstract base class for all SNA monitors. Defines the interface
that all lightweight, medium, and heavy monitors must implement.
"""

from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..types import MonitorConfig, MonitorResult, MonitorWeight

logger = logging.getLogger(__name__)

_SAFE_TABLE_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


# ──────────────────────────────────────────────────────────────
#  MONITOR BASE CLASS
# ──────────────────────────────────────────────────────────────

class MonitorBase(ABC):
    """Abstract base class for SNA monitors.

    Each monitor must implement:
      - check(): Execute the monitoring logic and return a MonitorResult
      - monitor_id: Unique identifier for this monitor type
      - monitor_name: Human-readable name
      - weight: Computational weight classification

    Monitors are stateless by design. State is managed by the
    SNA Engine via persistence and threshold configs.
    """

    @property
    @abstractmethod
    def monitor_id(self) -> str:
        """Unique identifier for this monitor type."""
        ...

    @property
    @abstractmethod
    def monitor_name(self) -> str:
        """Human-readable name of this monitor."""
        ...

    @property
    @abstractmethod
    def weight(self) -> MonitorWeight:
        """Computational weight classification."""
        ...

    @property
    def default_interval_seconds(self) -> float:
        """Default check interval in seconds."""
        from ..types import DEFAULT_INTERVALS
        return DEFAULT_INTERVALS.get(self.weight, 300.0)

    @property
    def description(self) -> str:
        """Short description of what this monitor checks."""
        return ""

    @abstractmethod
    async def check(self, params: Dict[str, Any],
                    tenant_id: str = "") -> MonitorResult:
        """Execute the monitoring check.

        Args:
            params: Monitor-specific parameters from MonitorConfig.
            tenant_id: Tenant context for data isolation.

        Returns:
            MonitorResult with triggered=True if condition detected.
        """
        ...

    def _make_result(
        self,
        triggered: bool,
        value: Any = None,
        detail: str = "",
        severity: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        start_time: float = 0.0,
    ) -> MonitorResult:
        """Helper to construct a MonitorResult with timing."""
        from ..types import AlertSeverity
        elapsed = (time.monotonic() - start_time) * 1000 if start_time else 0.0
        return MonitorResult(
            monitor_id=self.monitor_id,
            monitor_name=self.monitor_name,
            triggered=triggered,
            value=value,
            detail=detail,
            weight=self.weight,
            severity=AlertSeverity(severity) if severity else AlertSeverity.INFO,
            metadata=metadata or {},
            duration_ms=elapsed,
        )

    def _get_db_connection(self, db_name: str = "sna_data.sqlite"):
        """Get a database connection with tenant-aware isolation."""
        from src.core.shared.db_initializer import get_connection
        return get_connection(db_name)

    def _execute_query(
        self,
        query: str,
        params: tuple = (),
        db_name: str = "sna_data.sqlite",
    ) -> list:
        """Execute a read-only query and return rows."""
        try:
            conn = self._get_db_connection(db_name)
            conn.row_factory = None  # Return plain tuples
            return conn.execute(query, params).fetchall()
        except Exception as e:
            logger.warning(
                "Monitor %s: Query failed: %s", self.monitor_id, e,
            )
            return []

    def _execute_count(
        self,
        table: str,
        where: str = "",
        params: tuple = (),
        db_name: str = "sna_data.sqlite",
    ) -> int:
        """Execute a COUNT query and return the integer result."""
        if not _SAFE_TABLE_RE.match(table):
            logger.warning("Monitor %s: Invalid table name rejected: %s", self.monitor_id, table)
            return 0
        sql = f"SELECT COUNT(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"
        try:
            conn = self._get_db_connection(db_name)
            row = conn.execute(sql, params).fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.warning(
                "Monitor %s: Count query failed: %s", self.monitor_id, e,
            )
            return 0

    def _get_env_int(self, key: str, default: int = 0) -> int:
        """Read an integer from environment variables."""
        import os
        try:
            return int(os.environ.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    def _get_env_float(self, key: str, default: float = 0.0) -> float:
        """Read a float from environment variables."""
        import os
        try:
            return float(os.environ.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    def to_config(self, tenant_id: str = "",
                  blueprint_name: str = "") -> MonitorConfig:
        """Create a MonitorConfig from this monitor's defaults."""
        return MonitorConfig(
            monitor_id=self.monitor_id,
            monitor_name=self.monitor_name,
            weight=self.weight,
            interval_seconds=self.default_interval_seconds,
            tenant_id=tenant_id,
            blueprint_name=blueprint_name,
        )


# ──────────────────────────────────────────────────────────────
#  MONITOR REGISTRY
# ──────────────────────────────────────────────────────────────

_MONITOR_REGISTRY: Dict[str, type] = {}


def register_monitor(cls: type) -> type:
    """Decorator to register a monitor class in the global registry."""
    instance = cls()
    _MONITOR_REGISTRY[instance.monitor_id] = cls
    logger.debug("Registered SNA monitor: %s (%s)", instance.monitor_id, cls.__name__)
    return cls


def get_monitor_class(monitor_id: str) -> Optional[type]:
    """Get a monitor class by its ID."""
    return _MONITOR_REGISTRY.get(monitor_id)


def get_all_monitor_ids() -> list:
    """Get all registered monitor IDs."""
    return list(_MONITOR_REGISTRY.keys())


def create_monitor(monitor_id: str) -> Optional[MonitorBase]:
    """Create an instance of a monitor by ID."""
    cls = _MONITOR_REGISTRY.get(monitor_id)
    if cls is None:
        return None
    return cls()
