"""
ZENIC-AGENTS - Autonomy Level Management (Phase D1)

Defines autonomy levels and configuration for the autopilot system.
Controls how much freedom the system has to execute actions without
human approval, based on risk scores and autonomy level.

Autonomy levels:
  - SUPERVISED: Never auto-execute; always require approval.
  - SEMI_AUTONOMOUS: Auto-execute low-risk actions (< 0.2 risk).
  - FULL_AUTONOMOUS: Auto-execute actions below the approval threshold (< 0.5 risk).

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
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  ENUMS
# ──────────────────────────────────────────────────────────────

class AutonomyLevel(str, Enum):
    """Autonomy level of the autopilot system."""
    SUPERVISED = "supervised"
    SEMI_AUTONOMOUS = "semi_autonomous"
    FULL_AUTONOMOUS = "full_autonomous"


# ──────────────────────────────────────────────────────────────
#  DATACLASSES
# ──────────────────────────────────────────────────────────────

@dataclass
class AutonomyConfig:
    """Configuration for autopilot autonomy.

    Controls the degree of autonomous action the system can take,
    including risk thresholds for auto-execution vs. human approval.
    """
    level: AutonomyLevel = AutonomyLevel.SEMI_AUTONOMOUS
    objective_id: str = ""
    tenant_id: str = ""
    max_actions_per_cycle: int = 5
    requires_approval_above_risk: float = 0.5
    auto_approve_below_risk: float = 0.2
    notify_on_action: bool = True
    pause_on_exception: bool = True
    escalation_after_cycles: int = 3
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        """Set timestamps if not provided."""
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def can_auto_execute(self, risk_score: float) -> bool:
        """Check if an action with the given risk score can be auto-executed.

        SUPERVISED: Never auto-execute, always require approval.
        SEMI_AUTONOMOUS: Auto-execute if risk_score < auto_approve_below_risk.
        FULL_AUTONOMOUS: Auto-execute if risk_score < requires_approval_above_risk.

        Args:
            risk_score: Risk score of the action (0.0 to 1.0).

        Returns:
            True if the action can be executed without human approval.
        """
        if self.level == AutonomyLevel.SUPERVISED:
            return False
        if self.level == AutonomyLevel.SEMI_AUTONOMOUS:
            return risk_score < self.auto_approve_below_risk
        if self.level == AutonomyLevel.FULL_AUTONOMOUS:
            return risk_score < self.requires_approval_above_risk
        return False

    def requires_human_approval(self, risk_score: float) -> bool:
        """Check if an action with the given risk score requires human approval.

        Args:
            risk_score: Risk score of the action (0.0 to 1.0).

        Returns:
            True if the action requires human approval before execution.
        """
        return not self.can_auto_execute(risk_score)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "level": self.level.value,
            "objective_id": self.objective_id,
            "tenant_id": self.tenant_id,
            "max_actions_per_cycle": self.max_actions_per_cycle,
            "requires_approval_above_risk": self.requires_approval_above_risk,
            "auto_approve_below_risk": self.auto_approve_below_risk,
            "notify_on_action": self.notify_on_action,
            "pause_on_exception": self.pause_on_exception,
            "escalation_after_cycles": self.escalation_after_cycles,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AutonomyConfig:
        """Deserialize from dictionary.

        Args:
            data: Dictionary with autonomy config fields.

        Returns:
            A new AutonomyConfig instance.
        """
        level_raw = data.get("level", "semi_autonomous")
        return cls(
            level=AutonomyLevel(level_raw) if isinstance(level_raw, str) else level_raw,
            objective_id=data.get("objective_id", ""),
            tenant_id=data.get("tenant_id", ""),
            max_actions_per_cycle=data.get("max_actions_per_cycle", 5),
            requires_approval_above_risk=data.get("requires_approval_above_risk", 0.5),
            auto_approve_below_risk=data.get("auto_approve_below_risk", 0.2),
            notify_on_action=data.get("notify_on_action", True),
            pause_on_exception=data.get("pause_on_exception", True),
            escalation_after_cycles=data.get("escalation_after_cycles", 3),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


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
                "AutonomyConfigManager: DB retry %d/%d after %.2fs — %s",
                attempt + 1, max_retries, delay, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
        except Exception as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "AutonomyConfigManager: Unexpected error on retry %d/%d — %s",
                attempt + 1, max_retries, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────
#  AUTONOMY CONFIG MANAGER
# ──────────────────────────────────────────────────────────────

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

_autonomy_config_instance: Optional[AutonomyConfigManager] = None
_autonomy_config_lock = threading.Lock()


def get_autonomy_config(db_path: str = "autonomy_config.sqlite") -> AutonomyConfigManager:
    """Get or create the global AutonomyConfigManager instance.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        The singleton AutonomyConfigManager instance.
    """
    global _autonomy_config_instance
    with _autonomy_config_lock:
        if _autonomy_config_instance is None:
            _autonomy_config_instance = AutonomyConfigManager(db_path=db_path)
        return _autonomy_config_instance


def reset_autonomy_config() -> None:
    """Reset the global AutonomyConfigManager instance (for testing)."""
    global _autonomy_config_instance
    with _autonomy_config_lock:
        _autonomy_config_instance = None


__all__ = [
    "AutonomyLevel",
    "AutonomyConfig",
    "AutonomyConfigManager",
    "get_autonomy_config",
    "reset_autonomy_config",
]
