"""replay_queue — Persistence mixin (purge, stats, singleton)."""

from __future__ import annotations

import sqlite3
import threading
import time
from typing import Any

from ._types import *  # noqa: F403


class ReplayQueuePersistenceMixin:
    """Purge, stats, and singleton helpers for ReplayQueue."""

    # ── Purge ───────────────────────────────────────────────────

    def purge(
        self,
        tenant_id: str,
        older_than_hours: int = 168,
    ) -> int:
        """
        Remove old events from the dead-letter queue.

        Args:
            tenant_id: Filter by tenant.
            older_than_hours: Remove events older than this many hours
                              (default: 168 = 7 days).

        Returns:
            Number of events removed.
        """
        cutoff = time.time() - (older_than_hours * 3600)
        to_remove: list[str] = []

        with self._lock:
            for dlq_id, evt in self._events.items():
                if (
                    evt.tenant_id == tenant_id
                    and evt.created_at < cutoff
                    and evt.status in (
                        DeadLetterStatus.SUCCEEDED,  # noqa: F821
                        DeadLetterStatus.EXHAUSTED,  # noqa: F821
                    )
                ):
                    to_remove.append(dlq_id)

            for dlq_id in to_remove:
                del self._events[dlq_id]

        # Delete from DB
        if to_remove:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.executemany(
                    "DELETE FROM dead_letter_events WHERE dlq_id = ?",
                    [(did,) for did in to_remove],
                )
                conn.commit()
            finally:
                conn.close()

        __import__("logging").getLogger("zenic_agents.events.replay_queue").info(
            "ReplayQueue: purged %d events for tenant=%s older than %d hours",
            len(to_remove), tenant_id, older_than_hours,
        )
        return len(to_remove)

    # ── Stats ───────────────────────────────────────────────────

    def get_stats(
        self,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Get statistics about the dead-letter queue.

        Args:
            tenant_id: Optional tenant filter.

        Returns:
            Dict with counts by status, total, oldest event age, etc.
        """
        with self._lock:
            events = list(self._events.values())

        if tenant_id is not None:
            events = [e for e in events if e.tenant_id == tenant_id]

        status_counts: dict[str, int] = {
            s.value: 0 for s in DeadLetterStatus  # noqa: F821
        }
        oldest_created: float = time.time()
        total_retries = 0

        for evt in events:
            status_counts[evt.status.value] += 1
            total_retries += evt.retry_count
            if evt.created_at < oldest_created:
                oldest_created = evt.created_at

        now = time.time()
        oldest_age_hours = (
            (now - oldest_created) / 3600 if events else 0.0
        )

        return {
            "total": len(events),
            "by_status": status_counts,
            "total_retries": total_retries,
            "oldest_age_hours": round(oldest_age_hours, 2),
            "tenant_id": tenant_id,
        }


# ─── Singleton ──────────────────────────────────────────────────

_instance: ReplayQueue | None = None  # noqa: F821
_instance_lock = threading.Lock()


def get_replay_queue() -> "ReplayQueue":  # noqa: F821
    """Return the singleton ReplayQueue instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                from ._core import ReplayQueue
                _instance = ReplayQueue()
    return _instance


def reset_replay_queue() -> None:
    """Reset the singleton (mainly for testing)."""
    global _instance
    with _instance_lock:
        _instance = None
