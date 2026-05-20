"""
ZENIC-AGENTS — Snapshot Audit Helpers

Retry helper, diff computation, and singleton accessors.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from ._types import RETRY_BASE_DELAY, RETRY_MAX_ATTEMPTS, SnapshotDiff

logger = logging.getLogger(__name__)


# ── Retry helper ─────────────────────────────────────────────

def retry(fn: Callable[[], Any], label: str = "snapshot_audit_db_op") -> Any:
    """Execute *fn* with exponential backoff (3 retries, base 1 s)."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < RETRY_MAX_ATTEMPTS:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.debug(
                    "%s error (attempt %d/%d): %s — retrying in %.2fs",
                    label, attempt, RETRY_MAX_ATTEMPTS, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "%s failed after %d attempts: %s",
                    label, RETRY_MAX_ATTEMPTS, exc,
                )
    raise last_exc  # type: ignore[misc]


# ── Diff computation ─────────────────────────────────────────

def compute_diff(
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
                nested = compute_diff(old_val, new_val)
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


# ── Singleton ────────────────────────────────────────────────

_snapshot_audit_instance: Optional[Any] = None  # SnapshotAuditEngine
_snapshot_audit_lock = threading.Lock()


def get_snapshot_audit_engine(
    db_path: Optional[str] = None,
):
    """Get or create the singleton SnapshotAuditEngine.

    Args:
        db_path: Optional custom SQLite path for the snapshot audit DB.

    Returns:
        The shared SnapshotAuditEngine instance.
    """
    global _snapshot_audit_instance
    with _snapshot_audit_lock:
        if _snapshot_audit_instance is None:
            # Import here to avoid circular imports
            from ._snapshot import SnapshotAuditEngine
            _snapshot_audit_instance = SnapshotAuditEngine(db_path=db_path)
        return _snapshot_audit_instance


def reset_snapshot_audit_engine() -> None:
    """Reset the singleton SnapshotAuditEngine (for testing / reconfiguration)."""
    global _snapshot_audit_instance
    with _snapshot_audit_lock:
        _snapshot_audit_instance = None
    logger.info("SnapshotAuditEngine: singleton reset")
