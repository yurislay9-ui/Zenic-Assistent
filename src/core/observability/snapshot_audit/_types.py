"""
ZENIC-AGENTS — Snapshot Audit Types

Dataclasses and retry constants for the snapshot audit system.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# ── Retry constants ──────────────────────────────────────────
RETRY_MAX_ATTEMPTS: int = 3
RETRY_BASE_DELAY: float = 1.0  # 1 second base


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
