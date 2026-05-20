"""Snapshot Audit — Core engine and singleton."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from src.core.shared.db_initializer import get_data_dir
from ._types import (
from ._helpers import _init_db, _persist_snapshot, _update_pairing, _load_snapshot, _row_to_entry
    SnapshotEntry,
    SnapshotPair,
    SnapshotDiff,
    _retry,
    _compute_diff,
)

logger = logging.getLogger(__name__)


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

    @staticmethod