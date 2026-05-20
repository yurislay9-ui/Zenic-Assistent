"""Core logic for autonomy."""

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
from ._types import *
from ._helpers import *

logger = logging.getLogger(__name__)

class AutonomyConfigManager:
    """Manages autonomy configuration for objectives and tenants.

    Stores and retrieves AutonomyConfig instances from SQLite,
    providing per-objective and per-tenant autonomy settings.

    Thread-safe: All public methods guarded by RLock.
    """

    def __init__(self, db_path: str = "autonomy_config.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._initialized = False

    def _ensure_schema(self) -> None:
        """Create the autonomy config table if it does not exist."""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return

            def _init() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE TABLE IF NOT EXISTS _zenic_autonomy_configs (
                            config_id TEXT PRIMARY KEY,
                            level TEXT NOT NULL DEFAULT 'semi_autonomous',
                            objective_id TEXT NOT NULL DEFAULT '',
                            tenant_id TEXT NOT NULL DEFAULT '',
                            max_actions_per_cycle INTEGER NOT NULL DEFAULT 5,
                            requires_approval_above_risk REAL NOT NULL DEFAULT 0.5,
                            auto_approve_below_risk REAL NOT NULL DEFAULT 0.2,
                            notify_on_action INTEGER NOT NULL DEFAULT 1,
                            pause_on_exception INTEGER NOT NULL DEFAULT 1,
                            escalation_after_cycles INTEGER NOT NULL DEFAULT 3,
                            created_at TEXT NOT NULL DEFAULT '',
                            updated_at TEXT NOT NULL DEFAULT ''
                        )
                    """)
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE INDEX IF NOT EXISTS idx_zenic_aut_obj
                        ON _zenic_autonomy_configs(objective_id)
                    """)
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE INDEX IF NOT EXISTS idx_zenic_aut_tenant
                        ON _zenic_autonomy_configs(tenant_id)
                    """)
                    conn.commit()
                finally:
                    conn.close()

            _retry_db_operation(_init)
            self._initialized = True
            logger.info("AutonomyConfigManager: Schema initialized at %s", self._db_path)

    def get_config(
        self,
        objective_id: str = "",
        tenant_id: str = "",
    ) -> AutonomyConfig:
        """Get or create default autonomy config for an objective/tenant.

        If a config exists for the given objective_id, returns it.
        Otherwise, creates and returns a default config.

        Args:
            objective_id: Optional objective ID to get config for.
            tenant_id: Optional tenant ID to get config for.

        Returns:
            The AutonomyConfig for the specified scope.
        """
        self._ensure_schema()
        with self._lock:

            def _fetch() -> Optional[AutonomyConfig]:
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                try:
                    if objective_id:
                        row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                            """SELECT * FROM _zenic_autonomy_configs
                               WHERE objective_id = ? LIMIT 1""",
                            (objective_id,),
                        ).fetchone()
                    elif tenant_id:
                        row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                            """SELECT * FROM _zenic_autonomy_configs
                               WHERE tenant_id = ? AND objective_id = '' LIMIT 1""",
                            (tenant_id,),
                        ).fetchone()
                    else:
                        row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                            """SELECT * FROM _zenic_autonomy_configs
                               WHERE objective_id = '' AND tenant_id = '' LIMIT 1""",
                        ).fetchone()
                    if row is None:
                        return None
                    return self._row_to_config(row)
                finally:
                    conn.close()

            config = _retry_db_operation(_fetch)
            if config is not None:
                return config

        # Create default config
        default_config = AutonomyConfig(
            objective_id=objective_id,
            tenant_id=tenant_id,
        )
        self._persist_config(default_config)
        return default_config

    def update_config(self, config: AutonomyConfig) -> AutonomyConfig:
        """Update an existing autonomy config.

        Args:
            config: The AutonomyConfig with updated fields.

        Returns:
            The updated AutonomyConfig.
        """
        config.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist_config(config)
        logger.info(
            "AutonomyConfigManager: Updated config for objective %s (level=%s)",
            config.objective_id, config.level.value,
        )
        return config

    def set_level(
        self, objective_id: str, level: AutonomyLevel,
    ) -> AutonomyConfig:
        """Set the autonomy level for an objective.

        Args:
            objective_id: The objective ID to update.
            level: The new AutonomyLevel.

        Returns:
            The updated AutonomyConfig.
        """
        config = self.get_config(objective_id=objective_id)
        config.level = level
        return self.update_config(config)

    def list_configs(self, tenant_id: str = "") -> List[AutonomyConfig]:
        """List autonomy configs, optionally filtered by tenant.

        Args:
            tenant_id: Optional tenant ID filter.

        Returns:
            A list of matching AutonomyConfigs.
        """
        self._ensure_schema()
        with self._lock:

            def _list() -> List[AutonomyConfig]:
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                try:
                    if tenant_id:
                        rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                            """SELECT * FROM _zenic_autonomy_configs
                               WHERE tenant_id = ?
                               ORDER BY created_at DESC""",
                            (tenant_id,),
                        ).fetchall()
                    else:
                        rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                            """SELECT * FROM _zenic_autonomy_configs
                               ORDER BY created_at DESC""",
                        ).fetchall()
                    return [self._row_to_config(r) for r in rows]
                finally:
                    conn.close()

            return _retry_db_operation(_list)

    # ── Internal Helpers ────────────────────────────────────

    def _persist_config(self, config: AutonomyConfig) -> None:
        """Persist an autonomy config to the database.

        Uses INSERT OR REPLACE to handle both create and update.

        Args:
            config: The AutonomyConfig to persist.
        """
        self._ensure_schema()
        with self._lock:
            # Generate a stable config_id based on objective_id + tenant_id
            config_id = f"acfg-{uuid.uuid5(uuid.NAMESPACE_URL, config.objective_id + ':' + config.tenant_id).hex[:12]}"
            data = config.to_dict()

            def _upsert() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """INSERT OR REPLACE INTO _zenic_autonomy_configs
                           (config_id, level, objective_id, tenant_id,
                            max_actions_per_cycle, requires_approval_above_risk,
                            auto_approve_below_risk, notify_on_action,
                            pause_on_exception, escalation_after_cycles,
                            created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            config_id,
                            data["level"],
                            data["objective_id"],
                            data["tenant_id"],
                            data["max_actions_per_cycle"],
                            data["requires_approval_above_risk"],
                            data["auto_approve_below_risk"],
                            int(data["notify_on_action"]),
                            int(data["pause_on_exception"]),
                            data["escalation_after_cycles"],
                            data["created_at"],
                            data["updated_at"],
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

            _retry_db_operation(_upsert)

    @staticmethod
    def _row_to_config(row: sqlite3.Row) -> AutonomyConfig:
        """Convert a database row to an AutonomyConfig instance."""
        return AutonomyConfig(
            level=AutonomyLevel(row["level"]),
            objective_id=row["objective_id"],
            tenant_id=row["tenant_id"],
            max_actions_per_cycle=row["max_actions_per_cycle"],
            requires_approval_above_risk=row["requires_approval_above_risk"],
            auto_approve_below_risk=row["auto_approve_below_risk"],
            notify_on_action=bool(row["notify_on_action"]),
            pause_on_exception=bool(row["pause_on_exception"]),
            escalation_after_cycles=row["escalation_after_cycles"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

