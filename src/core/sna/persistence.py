"""
Zenic-Agents Asistente - SNA Persistence

SQLite/SQLCipher persistence layer for SNA alerts, thresholds,
and monitor history. Integrates with db_initializer for encrypted connections.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from .types import (
    Alert, AlertSeverity, AlertStatus, MonitorConfig, MonitorWeight,
    ThresholdConfig, ThresholdOperator,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  SCHEMA
# ──────────────────────────────────────────────────────────────

_SNA_DB = "sna_data.sqlite"

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS sna_alerts (
    alert_id TEXT PRIMARY KEY,
    monitor_id TEXT NOT NULL,
    monitor_name TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'warning',
    status TEXT NOT NULL DEFAULT 'pending',
    title TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    value TEXT,
    tenant_id TEXT NOT NULL DEFAULT '__anonymous__',
    channel TEXT NOT NULL DEFAULT 'log',
    dispatch_actions TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    dispatched_at REAL NOT NULL DEFAULT 0,
    notified_at REAL NOT NULL DEFAULT 0,
    acknowledged_at REAL NOT NULL DEFAULT 0,
    ttl_seconds REAL NOT NULL DEFAULT 3600
);

CREATE TABLE IF NOT EXISTS sna_thresholds (
    threshold_id TEXT PRIMARY KEY,
    monitor_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    operator TEXT NOT NULL,
    value REAL NOT NULL,
    value_high REAL,
    severity TEXT NOT NULL DEFAULT 'warning',
    cooldown_seconds REAL NOT NULL DEFAULT 300,
    tenant_id TEXT NOT NULL DEFAULT '__anonymous__',
    blueprint_name TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sna_monitor_configs (
    monitor_id TEXT PRIMARY KEY,
    monitor_name TEXT NOT NULL,
    weight TEXT NOT NULL DEFAULT 'lightweight',
    interval_seconds REAL NOT NULL DEFAULT 300,
    enabled INTEGER NOT NULL DEFAULT 1,
    tenant_id TEXT NOT NULL DEFAULT '__anonymous__',
    blueprint_name TEXT NOT NULL DEFAULT '',
    params TEXT NOT NULL DEFAULT '{}',
    notification_channel TEXT NOT NULL DEFAULT 'log',
    priority INTEGER NOT NULL DEFAULT 5
);

CREATE TABLE IF NOT EXISTS sna_check_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    monitor_id TEXT NOT NULL,
    triggered INTEGER NOT NULL DEFAULT 0,
    value TEXT,
    detail TEXT NOT NULL DEFAULT '',
    duration_ms REAL NOT NULL DEFAULT 0,
    checked_at REAL NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT '__anonymous__'
);

CREATE INDEX IF NOT EXISTS idx_sna_alerts_status ON sna_alerts(status);
CREATE INDEX IF NOT EXISTS idx_sna_alerts_tenant ON sna_alerts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sna_alerts_monitor ON sna_alerts(monitor_id);
CREATE INDEX IF NOT EXISTS idx_sna_alerts_created ON sna_alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_sna_thresholds_monitor ON sna_thresholds(monitor_id);
CREATE INDEX IF NOT EXISTS idx_sna_thresholds_tenant ON sna_thresholds(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sna_history_monitor ON sna_check_history(monitor_id);
CREATE INDEX IF NOT EXISTS idx_sna_history_tenant ON sna_check_history(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sna_history_time ON sna_check_history(checked_at);
"""


# ──────────────────────────────────────────────────────────────
#  PERSISTENCE LAYER
# ──────────────────────────────────────────────────────────────

class SNAPersistence:
    """SQLite/SQLCipher persistence for SNA data.

    Uses db_initializer for connection management,
    supporting encrypted connections when SQLCipher is available.
    """

    def __init__(self, db_name: str = _SNA_DB) -> None:
        self._db_name = db_name
        self._initialized = False

    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection via db_initializer."""
        from src.core.shared.db_initializer import get_connection
        return get_connection(self._db_name)

    def ensure_schema(self) -> None:
        """Create SNA tables if they don't exist."""
        if self._initialized:
            return
        from src.core.shared.db_initializer import write_lock
        conn = self._get_conn()
        with write_lock(self._db_name):
            conn.executescript(_CREATE_TABLES_SQL)
            conn.commit()
        self._initialized = True
        logger.info("SNAPersistence: Schema initialized for %s", self._db_name)

    # ── Alerts ─────────────────────────────────────────────

    def save_alert(self, alert: Alert) -> None:
        """Persist an alert to the database."""
        self.ensure_schema()
        from src.core.shared.db_initializer import write_lock
        conn = self._get_conn()
        with write_lock(self._db_name):
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT OR REPLACE INTO sna_alerts
                   (alert_id, monitor_id, monitor_name, severity, status,
                    title, message, value, tenant_id, channel,
                    dispatch_actions, metadata, created_at, dispatched_at,
                    notified_at, acknowledged_at, ttl_seconds)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (alert.alert_id, alert.monitor_id, alert.monitor_name,
                 alert.severity.value, alert.status.value,
                 alert.title, alert.message,
                 json.dumps(alert.value) if alert.value is not None else None,
                 alert.tenant_id, alert.channel,
                 json.dumps(alert.dispatch_actions),
                 json.dumps(alert.metadata),
                 alert.created_at, alert.dispatched_at,
                 alert.notified_at, alert.acknowledged_at,
                 alert.ttl_seconds),
            )
            conn.commit()

    def update_alert_status(self, alert_id: str, status: AlertStatus) -> None:
        """Update the status of an existing alert."""
        self.ensure_schema()
        from src.core.shared.db_initializer import write_lock
        conn = self._get_conn()
        now = time.time()
        extra_col = ""
        extra_val: List[Any] = []
        if status == AlertStatus.DISPATCHED:
            extra_col = ", dispatched_at = ?"
            extra_val = [now]
        elif status == AlertStatus.NOTIFIED:
            extra_col = ", notified_at = ?"
            extra_val = [now]
        elif status == AlertStatus.ACKNOWLEDGED:
            extra_col = ", acknowledged_at = ?"
            extra_val = [now]

        with write_lock(self._db_name):
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                f"UPDATE sna_alerts SET status = ?{extra_col} WHERE alert_id = ?",
                [status.value] + extra_val + [alert_id],
            )
            conn.commit()

    def get_active_alerts(self, tenant_id: str = "") -> List[Alert]:
        """Get all non-resolved, non-expired alerts."""
        self.ensure_schema()
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        if tenant_id:
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM sna_alerts WHERE status NOT IN ('resolved','expired') "
                "AND tenant_id = ? ORDER BY created_at DESC",
                (tenant_id,),
            ).fetchall()
        else:
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM sna_alerts WHERE status NOT IN ('resolved','expired') "
                "ORDER BY created_at DESC",
            ).fetchall()
        return [self._row_to_alert(r) for r in rows]

    # ── Thresholds ─────────────────────────────────────────

    def save_threshold(self, threshold: ThresholdConfig) -> None:
        """Persist a threshold configuration."""
        self.ensure_schema()
        from src.core.shared.db_initializer import write_lock
        conn = self._get_conn()
        with write_lock(self._db_name):
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT OR REPLACE INTO sna_thresholds
                   (threshold_id, monitor_id, field_name, operator,
                    value, value_high, severity, cooldown_seconds,
                    tenant_id, blueprint_name)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (threshold.threshold_id, threshold.monitor_id,
                 threshold.field_name, threshold.operator.value,
                 threshold.value, threshold.value_high,
                 threshold.severity.value, threshold.cooldown_seconds,
                 threshold.tenant_id, threshold.blueprint_name),
            )
            conn.commit()

    def get_thresholds(self, monitor_id: str = "", tenant_id: str = "") -> List[ThresholdConfig]:
        """Get threshold configurations, optionally filtered."""
        self.ensure_schema()
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        conditions: List[str] = []
        params: List[Any] = []
        if monitor_id:
            conditions.append("monitor_id = ?")
            params.append(monitor_id)
        if tenant_id:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
            f"SELECT * FROM sna_thresholds{where}", params,
        ).fetchall()
        return [self._row_to_threshold(r) for r in rows]

    # ── Monitor Configs ────────────────────────────────────

    def save_monitor_config(self, config: MonitorConfig) -> None:
        """Persist a monitor configuration."""
        self.ensure_schema()
        from src.core.shared.db_initializer import write_lock
        conn = self._get_conn()
        with write_lock(self._db_name):
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT OR REPLACE INTO sna_monitor_configs
                   (monitor_id, monitor_name, weight, interval_seconds,
                    enabled, tenant_id, blueprint_name, params,
                    notification_channel, priority)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (config.monitor_id, config.monitor_name,
                 config.weight.value, config.interval_seconds,
                 int(config.enabled), config.tenant_id,
                 config.blueprint_name, json.dumps(config.params),
                 config.notification_channel, config.priority),
            )
            conn.commit()

    def get_monitor_configs(self, tenant_id: str = "") -> List[MonitorConfig]:
        """Get all enabled monitor configurations."""
        self.ensure_schema()
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        if tenant_id:
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM sna_monitor_configs WHERE enabled = 1 AND tenant_id = ?",
                (tenant_id,),
            ).fetchall()
        else:
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM sna_monitor_configs WHERE enabled = 1",
            ).fetchall()
        return [self._row_to_monitor_config(r) for r in rows]

    # ── Check History ──────────────────────────────────────

    def record_check(self, monitor_id: str, triggered: bool,
                     value: Any, detail: str, duration_ms: float,
                     tenant_id: str = "") -> None:
        """Record a monitor check in history."""
        self.ensure_schema()
        from src.core.shared.db_initializer import write_lock
        conn = self._get_conn()
        with write_lock(self._db_name):
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT INTO sna_check_history
                   (monitor_id, triggered, value, detail, duration_ms, checked_at, tenant_id)
                   VALUES (?,?,?,?,?,?,?)""",
                (monitor_id, int(triggered),
                 json.dumps(value) if value is not None else None,
                 detail, duration_ms, time.time(),
                 tenant_id or "__anonymous__"),
            )
            conn.commit()

    def prune_history(self, older_than_days: int = 30) -> int:
        """Prune check history older than N days."""
        self.ensure_schema()
        from src.core.shared.db_initializer import write_lock
        conn = self._get_conn()
        cutoff = time.time() - (older_than_days * 86400)
        with write_lock(self._db_name):
            cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "DELETE FROM sna_check_history WHERE checked_at < ?", (cutoff,),
            )
            conn.commit()
            return cursor.rowcount

    # ── Row Converters ─────────────────────────────────────

    def _row_to_alert(self, row: sqlite3.Row) -> Alert:
        return Alert(
            alert_id=row["alert_id"],
            monitor_id=row["monitor_id"],
            monitor_name=row["monitor_name"],
            severity=AlertSeverity(row["severity"]),
            status=AlertStatus(row["status"]),
            title=row["title"],
            message=row["message"],
            value=json.loads(row["value"]) if row["value"] else None,
            tenant_id=row["tenant_id"],
            channel=row["channel"],
            dispatch_actions=json.loads(row["dispatch_actions"]),
            metadata=json.loads(row["metadata"]),
            created_at=row["created_at"],
            dispatched_at=row["dispatched_at"],
            notified_at=row["notified_at"],
            acknowledged_at=row["acknowledged_at"],
            ttl_seconds=row["ttl_seconds"],
        )

    def _row_to_threshold(self, row: sqlite3.Row) -> ThresholdConfig:
        return ThresholdConfig(
            threshold_id=row["threshold_id"],
            monitor_id=row["monitor_id"],
            field_name=row["field_name"],
            operator=ThresholdOperator(row["operator"]),
            value=row["value"],
            value_high=row["value_high"],
            severity=AlertSeverity(row["severity"]),
            cooldown_seconds=row["cooldown_seconds"],
            tenant_id=row["tenant_id"],
            blueprint_name=row["blueprint_name"],
        )

    def _row_to_monitor_config(self, row: sqlite3.Row) -> MonitorConfig:
        return MonitorConfig(
            monitor_id=row["monitor_id"],
            monitor_name=row["monitor_name"],
            weight=MonitorWeight(row["weight"]),
            interval_seconds=row["interval_seconds"],
            enabled=bool(row["enabled"]),
            tenant_id=row["tenant_id"],
            blueprint_name=row["blueprint_name"],
            params=json.loads(row["params"]),
            notification_channel=row["notification_channel"],
            priority=row["priority"],
        )
