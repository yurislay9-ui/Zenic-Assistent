"""
ZENIC-AGENTS — Snapshot Audit Engine (A1: Enriched Audit + Forensic Audit).

Before/After snapshot system that automatically captures data state
before and after CRUD operations.  Enables full change tracking,
diff computation, and point-in-time reconstruction of entity state.

Features:
- capture_before / capture_after for automatic state capture around mutations
- Deep diff computation (added, removed, changed keys with old/new values)
- Entity-level history queries with configurable limit
- Every DB operation wrapped in retry with exponential backoff (3 retries, base 1s)
- Thread-safe via threading.RLock
- SQLite persistence (snapshot_audit.sqlite)
- Singleton pattern with get_snapshot_audit_engine() / reset_snapshot_audit_engine()
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
from typing import Any, Dict, List, Optional

from src.core.shared.db_initializer import get_data_dir

logger = logging.getLogger(__name__)

# ── Retry constants ──────────────────────────────────────────
_RETRY_MAX_ATTEMPTS: int = 3
_RETRY_BASE_DELAY: float = 1.0  # 1 second base


# ── Dataclasses ──────────────────────────────────────────────

@dataclass
class SnapshotEntry:
    """A single snapshot of an entity's state at a point in time."""

    snapshot_id: str = ""
    entity_type: str = ""
    entity_id: str = ""
    tenant_id: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    captured_at: str = ""
    captured_at_epoch: float = 0.0
    snapshot_kind: str = ""  # "before" | "after"
    paired_snapshot_id: str = ""  # link to the other half of the pair
    pair_id: str = ""  # shared pair identifier

    def __post_init__(self) -> None:
        if not self.snapshot_id:
            self.snapshot_id = f"snap-{uuid.uuid4().hex[:12]}"
        if not self.captured_at:
            self.captured_at = datetime.now(timezone.utc).isoformat()
        if not self.captured_at_epoch:
            self.captured_at_epoch = time.time()


@dataclass
class SnapshotPair:
    """A before/after snapshot pair linked together."""

    pair_id: str = ""
    entity_type: str = ""
    entity_id: str = ""
    tenant_id: str = ""
    before: Optional[SnapshotEntry] = None
    after: Optional[SnapshotEntry] = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.pair_id:
            self.pair_id = f"spair-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class SnapshotDiff:
    """Diff between before and after snapshot states.

    Tracks added keys, removed keys, and changed keys with old/new values.
    """

    snapshot_id: str = ""
    pair_id: str = ""
    entity_type: str = ""
    entity_id: str = ""
    added: Dict[str, Any] = field(default_factory=dict)
    removed: Dict[str, Any] = field(default_factory=dict)
    changed: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "snapshot_id": self.snapshot_id,
            "pair_id": self.pair_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "added": self.added,
            "removed": self.removed,
            "changed": self.changed,
            "is_empty": self.is_empty,
        }


# ── Retry helper ─────────────────────────────────────────────

def _retry(fn, label: str = "snapshot_audit_db_op"):
    """Execute *fn* with exponential backoff (3 retries, base 1 s)."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < _RETRY_MAX_ATTEMPTS:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.debug(
                    "%s error (attempt %d/%d): %s — retrying in %.2fs",
                    label, attempt, _RETRY_MAX_ATTEMPTS, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "%s failed after %d attempts: %s",
                    label, _RETRY_MAX_ATTEMPTS, exc,
                )
    raise last_exc  # type: ignore[misc]


# ── Diff computation ─────────────────────────────────────────

def _compute_diff(
    before_data: Dict[str, Any],
    after_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute a deep diff between two dictionaries.

    Returns a dict with keys:
      - "added":   keys present in after but not in before, with their values
      - "removed": keys present in before but not in after, with their values
      - "changed": keys present in both but with different values;
                   each entry is {"old": <before_val>, "new": <after_val>}
    """
    added: Dict[str, Any] = {}
    removed: Dict[str, Any] = {}
    changed: Dict[str, Dict[str, Any]] = {}

    before_keys = set(before_data.keys())
    after_keys = set(after_data.keys())

    # Added keys
    for key in after_keys - before_keys:
        added[key] = after_data[key]

    # Removed keys
    for key in before_keys - after_keys:
        removed[key] = before_data[key]

    # Changed keys
    for key in before_keys & after_keys:
        old_val = before_data[key]
        new_val = after_data[key]
        if old_val != new_val:
            # If both are dicts, recurse for nested diff
            if isinstance(old_val, dict) and isinstance(new_val, dict):
                nested = _compute_diff(old_val, new_val)
                if nested["added"] or nested["removed"] or nested["changed"]:
                    changed[key] = {
                        "old": old_val,
                        "new": new_val,
                        "nested_diff": nested,
                    }
            else:
                changed[key] = {"old": old_val, "new": new_val}

    is_empty = not added and not removed and not changed
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "is_empty": is_empty,
    }


# ── SnapshotAuditEngine ──────────────────────────────────────

class SnapshotAuditEngine:
    """Before/After snapshot system for CRUD operation auditing.

    Thread-safe.  All DB operations are retried with exponential backoff.
    Persists snapshots to SQLite for long-term retention.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            db_path = str(get_data_dir() / "snapshot_audit.sqlite")
        self._db_path = db_path
        self._lock = threading.RLock()
        self._initialized = False
        self._init_db()

    # ── DB bootstrap ─────────────────────────────────────

    def _init_db(self) -> None:
        """Create the snapshot_audit SQLite schema."""

        def _create() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_snap_entity
                ON snapshots(entity_type, entity_id, tenant_id, captured_at_epoch DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_snap_pair
                ON snapshots(pair_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_snap_tenant
                ON snapshots(tenant_id, captured_at_epoch DESC)
            """)
            conn.execute("""
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

    def capture_before(
        self,
        entity_type: str,
        entity_id: str,
        data: Dict[str, Any],
        tenant_id: str,
    ) -> str:
        """Capture a "before" snapshot of entity state.

        Call this BEFORE performing a mutation (CREATE / UPDATE / DELETE).

        Args:
            entity_type: Type of entity (e.g. "user", "document", "config").
            entity_id: Unique identifier of the entity instance.
            data: Current entity state (will be deep-copied).
            tenant_id: Tenant scope.

        Returns:
            snapshot_id of the captured "before" snapshot.
        """
        snapshot = SnapshotEntry(
            entity_type=entity_type,
            entity_id=entity_id,
            tenant_id=tenant_id,
            data=data,
            snapshot_kind="before",
        )

        self._persist_snapshot(snapshot)

        logger.info(
            "SnapshotAuditEngine: capture_before %s/%s snap=%s tenant=%s",
            entity_type, entity_id, snapshot.snapshot_id, tenant_id,
        )
        return snapshot.snapshot_id

    def capture_after(
        self,
        entity_type: str,
        entity_id: str,
        data: Dict[str, Any],
        tenant_id: str,
        before_snapshot_id: str,
    ) -> SnapshotPair:
        """Capture an "after" snapshot and link it to the "before" snapshot.

        Call this AFTER performing a mutation.

        Args:
            entity_type: Type of entity (must match capture_before).
            entity_id: Entity identifier (must match capture_before).
            data: New entity state after mutation.
            tenant_id: Tenant scope.
            before_snapshot_id: The snapshot_id returned by capture_before.

        Returns:
            SnapshotPair linking the before and after snapshots.
        """
        # Create after snapshot
        pair_id = f"spair-{uuid.uuid4().hex[:12]}"

        after_snapshot = SnapshotEntry(
            entity_type=entity_type,
            entity_id=entity_id,
            tenant_id=tenant_id,
            data=data,
            snapshot_kind="after",
            paired_snapshot_id=before_snapshot_id,
        )

        # Load the before snapshot to create the pair
        before_snapshot = self._load_snapshot(before_snapshot_id)

        # Update the before snapshot with pairing info
        if before_snapshot is not None:
            before_snapshot.paired_snapshot_id = after_snapshot.snapshot_id
            self._update_pairing(
                before_snapshot_id,
                after_snapshot.snapshot_id,
                pair_id,
            )

        # Set pair_id on after snapshot
        after_snapshot.pair_id = pair_id
        self._persist_snapshot(after_snapshot)

        # Update after snapshot with pair_id
        self._update_pairing(
            after_snapshot.snapshot_id,
            before_snapshot_id,
            pair_id,
        )

        pair = SnapshotPair(
            pair_id=pair_id,
            entity_type=entity_type,
            entity_id=entity_id,
            tenant_id=tenant_id,
            before=before_snapshot,
            after=after_snapshot,
        )

        logger.info(
            "SnapshotAuditEngine: capture_after %s/%s pair=%s "
            "before=%s after=%s tenant=%s",
            entity_type, entity_id, pair_id,
            before_snapshot_id, after_snapshot.snapshot_id, tenant_id,
        )
        return pair

    def get_snapshot_pair(self, snapshot_id: str) -> Optional[SnapshotPair]:
        """Retrieve a before/after pair from either the before or after snapshot_id.

        Args:
            snapshot_id: The snapshot_id of either the "before" or "after" entry.

        Returns:
            SnapshotPair if found, None otherwise.
        """
        entry = self._load_snapshot(snapshot_id)
        if entry is None:
            return None

        # If this entry has a paired_snapshot_id, load the partner
        partner: Optional[SnapshotEntry] = None
        if entry.paired_snapshot_id:
            partner = self._load_snapshot(entry.paired_snapshot_id)

        # Determine before and after
        if entry.snapshot_kind == "before":
            before_entry = entry
            after_entry = partner
        elif entry.snapshot_kind == "after":
            before_entry = partner
            after_entry = entry
        else:
            before_entry = entry
            after_entry = partner

        # Resolve pair_id
        pair_id = entry.pair_id or f"spair-{uuid.uuid4().hex[:12]}"

        return SnapshotPair(
            pair_id=pair_id,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            tenant_id=entry.tenant_id,
            before=before_entry,
            after=after_entry,
        )

    def get_entity_history(
        self,
        entity_type: str,
        entity_id: str,
        tenant_id: str,
        limit: int = 100,
    ) -> List[SnapshotPair]:
        """Return all snapshot pairs (changes) for an entity, newest first.

        Args:
            entity_type: Type of entity.
            entity_id: Entity identifier.
            tenant_id: Tenant scope.
            limit: Maximum number of pairs to return.

        Returns:
            List of SnapshotPair objects ordered by capture time descending.
        """
        limit = max(1, min(limit, 1000))

        def _query() -> List[Dict[str, Any]]:
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM snapshots "
                    "WHERE entity_type = ? AND entity_id = ? AND tenant_id = ? "
                    "ORDER BY captured_at_epoch DESC "
                    "LIMIT ?",
                    (entity_type, entity_id, tenant_id, limit * 2),
                ).fetchall()
                conn.close()
            return [dict(r) for r in rows]

        try:
            raw_rows = _retry(_query, label="get_entity_history")
        except Exception as exc:
            logger.error("SnapshotAuditEngine: entity history query failed: %s", exc)
            return []

        # Group by pair_id to build pairs
        pairs_by_id: Dict[str, List[SnapshotEntry]] = {}
        unpaired: List[SnapshotEntry] = []

        for row in raw_rows:
            entry = self._row_to_entry(row)
            pid = row.get("pair_id") or ""
            if pid:
                pairs_by_id.setdefault(pid, []).append(entry)
            else:
                unpaired.append(entry)

        result: List[SnapshotPair] = []

        # Build pairs from pair_id groups
        for pid, entries in pairs_by_id.items():
            before_entry: Optional[SnapshotEntry] = None
            after_entry: Optional[SnapshotEntry] = None
            for e in entries:
                if e.snapshot_kind == "before":
                    before_entry = e
                elif e.snapshot_kind == "after":
                    after_entry = e

            # If we only have one side, try to load the partner
            if before_entry and not after_entry and before_entry.paired_snapshot_id:
                after_entry = self._load_snapshot(before_entry.paired_snapshot_id)
            if after_entry and not before_entry and after_entry.paired_snapshot_id:
                before_entry = self._load_snapshot(after_entry.paired_snapshot_id)

            result.append(SnapshotPair(
                pair_id=pid,
                entity_type=entity_type,
                entity_id=entity_id,
                tenant_id=tenant_id,
                before=before_entry,
                after=after_entry,
            ))

        # Handle unpaired entries (capture_before without capture_after yet)
        for entry in unpaired:
            partner: Optional[SnapshotEntry] = None
            if entry.paired_snapshot_id:
                partner = self._load_snapshot(entry.paired_snapshot_id)
            before_e = entry if entry.snapshot_kind == "before" else partner
            after_e = entry if entry.snapshot_kind == "after" else partner
            result.append(SnapshotPair(
                entity_type=entity_type,
                entity_id=entity_id,
                tenant_id=tenant_id,
                before=before_e,
                after=after_e,
            ))

        # Sort by the most recent captured_at_epoch in the pair (descending)
        result.sort(
            key=lambda p: max(
                p.before.captured_at_epoch if p.before else 0.0,
                p.after.captured_at_epoch if p.after else 0.0,
            ),
            reverse=True,
        )

        return result[:limit]

    def get_diff(self, snapshot_id: str) -> Dict[str, Any]:
        """Compute the diff between before and after states for a snapshot pair.

        Args:
            snapshot_id: The snapshot_id of either the "before" or "after" entry.

        Returns:
            Dict with keys "added", "removed", "changed", "is_empty".
            Each changed entry is {"old": <before_val>, "new": <after_val>}.
            Returns {"error": "..."} if the pair is incomplete.
        """
        pair = self.get_snapshot_pair(snapshot_id)
        if pair is None:
            return {"error": f"Snapshot not found: {snapshot_id}"}

        if pair.before is None or pair.after is None:
            return {
                "error": "Incomplete pair: both before and after snapshots required",
                "snapshot_id": snapshot_id,
                "has_before": pair.before is not None,
                "has_after": pair.after is not None,
            }

        diff_result = _compute_diff(pair.before.data, pair.after.data)

        diff = SnapshotDiff(
            snapshot_id=snapshot_id,
            pair_id=pair.pair_id,
            entity_type=pair.entity_type,
            entity_id=pair.entity_id,
            added=diff_result["added"],
            removed=diff_result["removed"],
            changed=diff_result["changed"],
            is_empty=diff_result["is_empty"],
        )

        logger.debug(
            "SnapshotAuditEngine: get_diff snap=%s added=%d removed=%d changed=%d",
            snapshot_id, len(diff.added), len(diff.removed), len(diff.changed),
        )
        return diff.to_dict()

    # ── Internal helpers ─────────────────────────────────

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
                conn.execute(
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
                conn.execute(
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
                row = conn.execute(
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

    @staticmethod
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
