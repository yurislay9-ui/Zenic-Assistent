"""
ZENIC-AGENTS — SnapshotAuditEngine: Database Helpers

Standalone functions for DB persistence and row conversion,
extracted from SnapshotAuditEngine to keep the main module under 400 lines.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from ._audit import retry
from ._types import SnapshotEntry

logger = logging.getLogger(__name__)


# ── DB bootstrap ─────────────────────────────────────────────

def init_db(db_path: str) -> bool:
    """Create the snapshot_audit SQLite schema.

    Returns True if initialization succeeded, False otherwise.
    """
    def _create() -> None:
        conn = sqlite3.connect(db_path)
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
        retry(_create, label="SnapshotAuditEngine._init_db")
        logger.info(
            "SnapshotAuditEngine: Database initialized at %s",
            db_path,
        )
        return True
    except Exception as exc:
        logger.error(
            "SnapshotAuditEngine: Database initialization failed: %s",
            exc,
        )
        return False


# ── Row Conversion ──────────────────────────────────────────

def row_to_entry(row: Dict[str, Any]) -> SnapshotEntry:
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


# ── Persistence ─────────────────────────────────────────────

def persist_snapshot(
    snapshot: SnapshotEntry,
    db_path: str,
    lock: threading.RLock,
    initialized: bool,
) -> None:
    """Write a SnapshotEntry to SQLite."""
    if not initialized:
        logger.warning(
            "SnapshotAuditEngine: DB not initialized, skipping persist for %s",
            snapshot.snapshot_id,
        )
        return

    def _insert() -> None:
        with lock:
            conn = sqlite3.connect(db_path)
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
        retry(_insert, label="SnapshotAuditEngine._persist_snapshot")
    except Exception as exc:
        logger.error(
            "SnapshotAuditEngine: failed to persist snapshot %s: %s",
            snapshot.snapshot_id, exc,
        )


def update_pairing(
    snapshot_id: str,
    paired_snapshot_id: str,
    pair_id: str,
    db_path: str,
    lock: threading.RLock,
) -> None:
    """Update the paired_snapshot_id and pair_id for an existing snapshot."""

    def _update() -> None:
        with lock:
            conn = sqlite3.connect(db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "UPDATE snapshots SET paired_snapshot_id = ?, pair_id = ? "
                "WHERE snapshot_id = ?",
                (paired_snapshot_id, pair_id, snapshot_id),
            )
            conn.commit()
            conn.close()

    try:
        retry(_update, label="SnapshotAuditEngine._update_pairing")
    except Exception as exc:
        logger.error(
            "SnapshotAuditEngine: failed to update pairing for %s: %s",
            snapshot_id, exc,
        )


# ── Queries ─────────────────────────────────────────────────

def load_snapshot(
    snapshot_id: str,
    db_path: str,
    lock: threading.RLock,
) -> Optional[SnapshotEntry]:
    """Load a single SnapshotEntry from SQLite by snapshot_id."""

    def _query() -> Optional[SnapshotEntry]:
        with lock:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
            conn.close()
        if row is None:
            return None
        return row_to_entry(dict(row))

    try:
        return retry(_query, label="SnapshotAuditEngine._load_snapshot")
    except Exception as exc:
        logger.error(
            "SnapshotAuditEngine: failed to load snapshot %s: %s",
            snapshot_id, exc,
        )
        return None


def query_entity_history(
    entity_type: str,
    entity_id: str,
    tenant_id: str,
    limit: int,
    db_path: str,
    lock: threading.RLock,
) -> List[Dict[str, Any]]:
    """Query raw snapshot rows for entity history."""
    def _query() -> List[Dict[str, Any]]:
        with lock:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM snapshots "
                "WHERE entity_type = ? AND entity_id = ? AND tenant_id = ? "
                "ORDER BY captured_at_epoch DESC "
                "LIMIT ?",
                (entity_type, entity_id, tenant_id, limit * 2),
            ).fetchall()
            conn.close()
        return [dict(r) for r in rows]

    try:
        return retry(_query, label="get_entity_history")
    except Exception as exc:
        logger.error("SnapshotAuditEngine: entity history query failed: %s", exc)
        return []
