"""Helper methods extracted from snapshot_audit."""

from __future__ import annotations

import json
import sqlite3
from ._types import SnapshotEntry, _retry

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


    def _init_db(self) -> None:
        """Create the snapshot_audit SQLite schema."""

        def _create() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    captured_at_epoch REAL NOT NULL,
                    snapshot_kind TEXT NOT NULL,
                    paired_snapshot_id TEXT NOT NULL DEFAULT '',
                    pair_id TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_snap_entity
                ON snapshots(entity_type, entity_id, tenant_id, captured_at_epoch DESC)
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_snap_pair
                ON snapshots(pair_id)
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_snap_tenant
                ON snapshots(tenant_id, captured_at_epoch DESC)
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_snap_paired
                ON snapshots(paired_snapshot_id)
            """)
            conn.commit()
            conn.close()

        try:
            _retry(_create, label="SnapshotAuditEngine._init_db")
            self._initialized = True
            logger.info(
                "SnapshotAuditEngine: Database initialized at %s",
                self._db_path,
            )
        except Exception as exc:
            logger.error(
                "SnapshotAuditEngine: Database initialization failed: %s",
                exc,
            )
            self._initialized = False

    # ── Public API ───────────────────────────────────────


    def _persist_snapshot(self, snapshot: SnapshotEntry) -> None:
        """Write a SnapshotEntry to SQLite."""
        if not self._initialized:
            logger.warning(
                "SnapshotAuditEngine: DB not initialized, skipping persist for %s",
                snapshot.snapshot_id,
            )
            return

        def _insert() -> None:
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO snapshots
                       (snapshot_id, entity_type, entity_id, tenant_id,
                        data, captured_at, captured_at_epoch,
                        snapshot_kind, paired_snapshot_id, pair_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        snapshot.snapshot_id,
                        snapshot.entity_type,
                        snapshot.entity_id,
                        snapshot.tenant_id,
                        json.dumps(snapshot.data, ensure_ascii=False, default=str),
                        snapshot.captured_at,
                        snapshot.captured_at_epoch,
                        snapshot.snapshot_kind,
                        snapshot.paired_snapshot_id,
                        snapshot.pair_id,
                    ),
                )
                conn.commit()
                conn.close()

        try:
            _retry(_insert, label="SnapshotAuditEngine._persist_snapshot")
        except Exception as exc:
            logger.error(
                "SnapshotAuditEngine: failed to persist snapshot %s: %s",
                snapshot.snapshot_id, exc,
            )


    def _update_pairing(
        self,
        snapshot_id: str,
        paired_snapshot_id: str,
        pair_id: str,
    ) -> None:
        """Update the paired_snapshot_id and pair_id for an existing snapshot."""

        def _update() -> None:
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "UPDATE snapshots SET paired_snapshot_id = ?, pair_id = ? "
                    "WHERE snapshot_id = ?",
                    (paired_snapshot_id, pair_id, snapshot_id),
                )
                conn.commit()
                conn.close()

        try:
            _retry(_update, label="SnapshotAuditEngine._update_pairing")
        except Exception as exc:
            logger.error(
                "SnapshotAuditEngine: failed to update pairing for %s: %s",
                snapshot_id, exc,
            )


    def _load_snapshot(self, snapshot_id: str) -> Optional[SnapshotEntry]:
        """Load a single SnapshotEntry from SQLite by snapshot_id."""

        def _query() -> Optional[SnapshotEntry]:
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT * FROM snapshots WHERE snapshot_id = ?",
                    (snapshot_id,),
                ).fetchone()
                conn.close()
            if row is None:
                return None
            return self._row_to_entry(dict(row))

        try:
            return _retry(_query, label="SnapshotAuditEngine._load_snapshot")
        except Exception as exc:
            logger.error(
                "SnapshotAuditEngine: failed to load snapshot %s: %s",
                snapshot_id, exc,
            )
            return None


    def _row_to_entry(row: Dict[str, Any]) -> SnapshotEntry:
        """Convert a raw DB row dict to a SnapshotEntry."""
        data_raw = row.get("data", "{}")
        if isinstance(data_raw, str):
            try:
                data = json.loads(data_raw)
            except (json.JSONDecodeError, TypeError):
                data = {"_raw": data_raw}
        elif isinstance(data_raw, dict):
            data = data_raw
        else:
            data = {}

        return SnapshotEntry(
            snapshot_id=row.get("snapshot_id", ""),
            entity_type=row.get("entity_type", ""),
            entity_id=row.get("entity_id", ""),
            tenant_id=row.get("tenant_id", ""),
            data=data,
            captured_at=row.get("captured_at", ""),
            captured_at_epoch=row.get("captured_at_epoch", 0.0),
            snapshot_kind=row.get("snapshot_kind", ""),
            paired_snapshot_id=row.get("paired_snapshot_id", ""),
            pair_id=row.get("pair_id", ""),
        )


# ── Singleton ────────────────────────────────────────────────

_snapshot_audit_instance: Optional[SnapshotAuditEngine] = None
_snapshot_audit_lock = threading.Lock()


def get_snapshot_audit_engine(
    db_path: Optional[str] = None,
) -> SnapshotAuditEngine:
    """Get or create the singleton SnapshotAuditEngine.

    Args:
        db_path: Optional custom SQLite path for the snapshot audit DB.

    Returns:
        The shared SnapshotAuditEngine instance.
    """
    global _snapshot_audit_instance
    with _snapshot_audit_lock:
        if _snapshot_audit_instance is None:
            _snapshot_audit_instance = SnapshotAuditEngine(db_path=db_path)
        return _snapshot_audit_instance


def reset_snapshot_audit_engine() -> None:
    """Reset the singleton SnapshotAuditEngine (for testing / reconfiguration)."""
    global _snapshot_audit_instance
    with _snapshot_audit_lock:
        _snapshot_audit_instance = None
    logger.info("SnapshotAuditEngine: singleton reset")


# ── Module exports ───────────────────────────────────────────

__all__ = [
    # Dataclasses
    "SnapshotEntry",
    "SnapshotPair",
    "SnapshotDiff",
    # Engine
    "SnapshotAuditEngine",
    # Singleton
    "get_snapshot_audit_engine",
    "reset_snapshot_audit_engine",
]

