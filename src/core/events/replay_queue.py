"""
ZENIC-AGENTS — ReplayQueue (B1: Event-driven Actions Engine)

Dead-letter queue with event replay capability. Failed events are
stored with their error details and can be retried individually or
in batch, with exponential backoff.

Usage:
    dlq = ReplayQueue()
    dlq_id = dlq.enqueue("db.stock_below", {"entity_id": "AAPL", "value": 5.0},
                          "Connection timeout", "tenant_1")
    result = dlq.retry_event(dlq_id)
    stats = dlq.get_stats("tenant_1")
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .trigger_map import TriggerMap, get_trigger_map

logger = logging.getLogger("zenic_agents.events.replay_queue")

DB_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "db")
DB_PATH = os.path.join(DB_DIR, "replay_queue.sqlite")

# Retry configuration
DEFAULT_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # seconds — yields 1s, 2s, 4s


# ─── Enums ──────────────────────────────────────────────────────

class DeadLetterStatus(str, Enum):
    """Status of a dead-letter event."""
    PENDING = "pending"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    EXHAUSTED = "exhausted"


# ─── Dataclasses ────────────────────────────────────────────────

@dataclass
class DeadLetterEvent:
    """
    A failed event stored in the dead-letter queue.

    Attributes:
        dlq_id: Unique identifier.
        event_type: The event type that failed.
        event_data: The original event payload.
        error: Description of the failure.
        tenant_id: Owner tenant.
        retry_count: Number of retry attempts so far.
        max_retries: Maximum allowed retries (default 3).
        last_retry_at: Timestamp of last retry attempt, or 0.0.
        created_at: Unix timestamp when enqueued.
        status: Current status.
    """
    dlq_id: str
    event_type: str
    event_data: dict[str, Any]
    error: str
    tenant_id: str
    retry_count: int = 0
    max_retries: int = DEFAULT_MAX_RETRIES
    last_retry_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    status: DeadLetterStatus = DeadLetterStatus.PENDING


@dataclass
class RetryResult:
    """
    Result of retrying a single dead-letter event.

    Attributes:
        success: Whether the retry dispatch succeeded.
        dlq_id: The event's DLQ identifier.
        event_type: The event type.
        retry_count: Updated retry count.
        status: Updated status.
        error: Error message if retry failed, empty string otherwise.
    """
    success: bool
    dlq_id: str
    event_type: str
    retry_count: int = 0
    status: DeadLetterStatus = DeadLetterStatus.PENDING
    error: str = ""


@dataclass
class BatchRetryResult:
    """
    Result of retrying a batch of dead-letter events.

    Attributes:
        total_attempted: Number of events selected for retry.
        succeeded: Number that dispatched successfully.
        failed: Number that failed again.
        exhausted: Number that hit max retries.
        details: Per-event RetryResult list.
    """
    total_attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    exhausted: int = 0
    details: list[RetryResult] = field(default_factory=list)


# ─── Serialization ──────────────────────────────────────────────

def _event_from_row(row: sqlite3.Row) -> DeadLetterEvent:
    """Deserialize a DeadLetterEvent from a SQLite row."""
    event_data_raw = row["event_data_json"]
    try:
        event_data = json.loads(event_data_raw)
    except (json.JSONDecodeError, TypeError):
        event_data = {}

    return DeadLetterEvent(
        dlq_id=row["dlq_id"],
        event_type=row["event_type"],
        event_data=event_data,
        error=row["error"],
        tenant_id=row["tenant_id"],
        retry_count=row["retry_count"],
        max_retries=row["max_retries"],
        last_retry_at=row["last_retry_at"],
        created_at=row["created_at"],
        status=DeadLetterStatus(row["status"]),
    )


# ─── ReplayQueue ────────────────────────────────────────────────

class ReplayQueue:
    """
    Dead-letter queue with event replay capability.

    Failed events are stored with error details and can be retried
    individually or in batch with exponential backoff (1s, 2s, 4s).
    After max_retries, events are marked as exhausted.

    Thread-safe with RLock. Persisted to SQLite.
    Singleton pattern via get_replay_queue() / reset_replay_queue().
    """

    def __init__(
        self,
        db_path: str | None = None,
        trigger_map: TriggerMap | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._db_path = db_path or DB_PATH
        self._events: dict[str, DeadLetterEvent] = {}
        self._trigger_map = trigger_map
        self._initialized = False
        self._init_db()
        self._load_from_db()

    # ── Lazy dependency injection ───────────────────────────────

    @property
    def trigger_map(self) -> TriggerMap:
        if self._trigger_map is None:
            self._trigger_map = get_trigger_map()
        return self._trigger_map

    # ── DB Setup ────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Initialize the SQLite database."""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dead_letter_events (
                    dlq_id          TEXT PRIMARY KEY,
                    event_type      TEXT NOT NULL,
                    event_data_json TEXT NOT NULL DEFAULT '{}',
                    error           TEXT NOT NULL DEFAULT '',
                    tenant_id       TEXT NOT NULL,
                    retry_count     INTEGER NOT NULL DEFAULT 0,
                    max_retries     INTEGER NOT NULL DEFAULT 3,
                    last_retry_at   REAL NOT NULL DEFAULT 0.0,
                    created_at      REAL NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'pending'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dlq_tenant_status
                ON dead_letter_events(tenant_id, status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dlq_status
                ON dead_letter_events(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dlq_created
                ON dead_letter_events(created_at)
            """)
            conn.commit()
        finally:
            conn.close()
        self._initialized = True

    def _load_from_db(self) -> None:
        """Load all events from SQLite into memory."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM dead_letter_events"
            ).fetchall()
            with self._lock:
                for row in rows:
                    evt = _event_from_row(row)
                    self._events[evt.dlq_id] = evt
        finally:
            conn.close()
        logger.info(
            "ReplayQueue: loaded %d events from %s",
            len(self._events), self._db_path,
        )

    def _persist_event(self, evt: DeadLetterEvent) -> None:
        """Write or update an event in SQLite."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO dead_letter_events
                    (dlq_id, event_type, event_data_json, error, tenant_id,
                     retry_count, max_retries, last_retry_at, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evt.dlq_id,
                    evt.event_type,
                    json.dumps(evt.event_data),
                    evt.error,
                    evt.tenant_id,
                    evt.retry_count,
                    evt.max_retries,
                    evt.last_retry_at,
                    evt.created_at,
                    evt.status.value,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _delete_event(self, dlq_id: str) -> None:
        """Delete an event from SQLite."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                "DELETE FROM dead_letter_events WHERE dlq_id = ?",
                (dlq_id,),
            )
            conn.commit()
        finally:
            conn.close()

    # ── Enqueue ─────────────────────────────────────────────────

    def enqueue(
        self,
        event_type: str,
        event_data: dict[str, Any],
        error: str,
        tenant_id: str,
    ) -> str:
        """
        Add a failed event to the dead-letter queue.

        Args:
            event_type: The event type that failed.
            event_data: The original event payload.
            error: Description of the failure.
            tenant_id: Owner tenant.

        Returns:
            dlq_id (unique string).
        """
        if not event_type or not isinstance(event_type, str):
            raise ValueError("event_type must be a non-empty string")
        if not isinstance(event_data, dict):
            raise ValueError("event_data must be a dict")
        if not tenant_id or not isinstance(tenant_id, str):
            raise ValueError("tenant_id must be a non-empty string")

        dlq_id = f"dlq_{uuid.uuid4().hex[:12]}"
        evt = DeadLetterEvent(
            dlq_id=dlq_id,
            event_type=event_type,
            event_data=event_data,
            error=error,
            tenant_id=tenant_id,
            retry_count=0,
            max_retries=DEFAULT_MAX_RETRIES,
            last_retry_at=0.0,
            created_at=time.time(),
            status=DeadLetterStatus.PENDING,
        )

        with self._lock:
            self._events[dlq_id] = evt
        self._persist_event(evt)

        logger.info(
            "ReplayQueue: enqueued %s (event_type=%s, tenant=%s, error='%s')",
            dlq_id, event_type, tenant_id, error[:100],
        )
        return dlq_id

    # ── Dequeue ─────────────────────────────────────────────────

    def dequeue(self, dlq_id: str) -> DeadLetterEvent | None:
        """
        Get a specific dead-letter event by ID.

        Returns:
            The DeadLetterEvent, or None if not found.
        """
        with self._lock:
            return self._events.get(dlq_id)

    # ── List Pending ────────────────────────────────────────────

    def list_pending(
        self,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[DeadLetterEvent]:
        """
        List events pending retry.

        Args:
            tenant_id: Filter by tenant (None = all tenants).
            limit: Maximum number of events to return.

        Returns:
            List of DeadLetterEvent objects in pending/retrying status.
        """
        with self._lock:
            events = list(self._events.values())

        result = []
        for evt in events:
            if evt.status not in (DeadLetterStatus.PENDING, DeadLetterStatus.RETRYING):
                continue
            if tenant_id is not None and evt.tenant_id != tenant_id:
                continue
            result.append(evt)
            if len(result) >= limit:
                break

        result.sort(key=lambda e: e.created_at)
        return result

    # ── Retry Single Event ──────────────────────────────────────

    def retry_event(self, dlq_id: str) -> RetryResult:
        """
        Re-dispatch a single event through the TriggerMap.

        Applies exponential backoff between retries:
          - 1st retry: 1s backoff
          - 2nd retry: 2s backoff
          - 3rd retry: 4s backoff

        After max_retries, the event status becomes exhausted.

        Args:
            dlq_id: The dead-letter event ID.

        Returns:
            RetryResult with outcome details.
        """
        with self._lock:
            evt = self._events.get(dlq_id)

        if evt is None:
            return RetryResult(
                success=False,
                dlq_id=dlq_id,
                event_type="",
                error=f"No dead-letter event found with id {dlq_id}",
            )

        if evt.status == DeadLetterStatus.EXHAUSTED:
            return RetryResult(
                success=False,
                dlq_id=dlq_id,
                event_type=evt.event_type,
                retry_count=evt.retry_count,
                status=evt.status,
                error="Event is exhausted (max retries reached)",
            )

        if evt.status == DeadLetterStatus.SUCCEEDED:
            return RetryResult(
                success=False,
                dlq_id=dlq_id,
                event_type=evt.event_type,
                retry_count=evt.retry_count,
                status=evt.status,
                error="Event already succeeded",
            )

        # Update status to retrying
        with self._lock:
            evt.status = DeadLetterStatus.RETRYING
            evt.retry_count += 1
            evt.last_retry_at = time.time()
        self._persist_event(evt)

        # Apply exponential backoff
        if evt.retry_count > 1:
            backoff = _BACKOFF_BASE * (2 ** (evt.retry_count - 1))
            time.sleep(backoff)

        # Attempt dispatch
        try:
            matches = self.trigger_map.lookup(evt.event_type, evt.event_data)
            dispatch_ok = True
            dispatch_error = ""
            if not matches:
                logger.debug(
                    "ReplayQueue: no automations matched event %s on retry %d",
                    evt.event_type, evt.retry_count,
                )
        except Exception as exc:
            dispatch_ok = False
            dispatch_error = str(exc)
            logger.warning(
                "ReplayQueue: dispatch error for %s on retry %d: %s",
                evt.dlq_id, evt.retry_count, exc,
            )

        if dispatch_ok:
            with self._lock:
                evt.status = DeadLetterStatus.SUCCEEDED
            self._persist_event(evt)
            logger.info(
                "ReplayQueue: retry succeeded for %s after %d attempt(s)",
                dlq_id, evt.retry_count,
            )
            return RetryResult(
                success=True,
                dlq_id=dlq_id,
                event_type=evt.event_type,
                retry_count=evt.retry_count,
                status=evt.status,
            )
        else:
            # Check if exhausted
            if evt.retry_count >= evt.max_retries:
                with self._lock:
                    evt.status = DeadLetterStatus.EXHAUSTED
                    evt.error = dispatch_error or "Max retries reached"
                self._persist_event(evt)
                logger.warning(
                    "ReplayQueue: %s exhausted after %d retries",
                    dlq_id, evt.retry_count,
                )
                return RetryResult(
                    success=False,
                    dlq_id=dlq_id,
                    event_type=evt.event_type,
                    retry_count=evt.retry_count,
                    status=evt.status,
                    error=dispatch_error or "Max retries reached",
                )
            else:
                with self._lock:
                    evt.status = DeadLetterStatus.PENDING
                    evt.error = dispatch_error or "Retry failed"
                self._persist_event(evt)
                return RetryResult(
                    success=False,
                    dlq_id=dlq_id,
                    event_type=evt.event_type,
                    retry_count=evt.retry_count,
                    status=evt.status,
                    error=dispatch_error or "Retry failed",
                )

    # ── Batch Retry ─────────────────────────────────────────────

    def retry_batch(
        self,
        tenant_id: str,
        event_type: str | None = None,
    ) -> BatchRetryResult:
        """
        Retry all matching pending/retrying events for a tenant.

        Args:
            tenant_id: Filter by tenant.
            event_type: Optional event type filter.

        Returns:
            BatchRetryResult with aggregate and per-event details.
        """
        candidates = self.list_pending(tenant_id=tenant_id, limit=10000)
        if event_type is not None:
            candidates = [e for e in candidates if e.event_type == event_type]

        result = BatchRetryResult(total_attempted=len(candidates))

        for evt in candidates:
            rr = self.retry_event(evt.dlq_id)
            result.details.append(rr)
            if rr.success:
                result.succeeded += 1
            else:
                result.failed += 1
                if rr.status == DeadLetterStatus.EXHAUSTED:
                    result.exhausted += 1

        logger.info(
            "ReplayQueue: batch retry for tenant=%s event_type=%s — "
            "attempted=%d, succeeded=%d, failed=%d, exhausted=%d",
            tenant_id, event_type,
            result.total_attempted, result.succeeded,
            result.failed, result.exhausted,
        )
        return result

    # ── Replay Since ────────────────────────────────────────────

    def replay_since(
        self,
        since_timestamp: float,
        tenant_id: str | None = None,
    ) -> BatchRetryResult:
        """
        Replay all events created since a given timestamp.

        Args:
            since_timestamp: Unix timestamp. Events created at or after
                             this time will be retried.
            tenant_id: Optional tenant filter.

        Returns:
            BatchRetryResult with aggregate and per-event details.
        """
        with self._lock:
            candidates = [
                evt for evt in self._events.values()
                if evt.created_at >= since_timestamp
                and evt.status in (DeadLetterStatus.PENDING, DeadLetterStatus.RETRYING)
                and (tenant_id is None or evt.tenant_id == tenant_id)
            ]

        candidates.sort(key=lambda e: e.created_at)
        result = BatchRetryResult(total_attempted=len(candidates))

        for evt in candidates:
            rr = self.retry_event(evt.dlq_id)
            result.details.append(rr)
            if rr.success:
                result.succeeded += 1
            else:
                result.failed += 1
                if rr.status == DeadLetterStatus.EXHAUSTED:
                    result.exhausted += 1

        logger.info(
            "ReplayQueue: replay_since(ts=%.1f, tenant=%s) — "
            "attempted=%d, succeeded=%d, failed=%d, exhausted=%d",
            since_timestamp, tenant_id,
            result.total_attempted, result.succeeded,
            result.failed, result.exhausted,
        )
        return result

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
                        DeadLetterStatus.SUCCEEDED,
                        DeadLetterStatus.EXHAUSTED,
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

        logger.info(
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
            s.value: 0 for s in DeadLetterStatus
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

_instance: ReplayQueue | None = None
_instance_lock = threading.Lock()


def get_replay_queue() -> ReplayQueue:
    """Return the singleton ReplayQueue instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ReplayQueue()
    return _instance


def reset_replay_queue() -> None:
    """Reset the singleton (mainly for testing)."""
    global _instance
    with _instance_lock:
        _instance = None


__all__ = [
    "ReplayQueue",
    "DeadLetterEvent",
    "DeadLetterStatus",
    "RetryResult",
    "BatchRetryResult",
    "get_replay_queue",
    "reset_replay_queue",
]
