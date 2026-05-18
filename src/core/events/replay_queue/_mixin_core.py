"""replay_queue — Core mixin (enqueue, dequeue, retry, batch, replay)."""

from __future__ import annotations

import time
from typing import Any

from ._types import *  # noqa: F403
from ._helpers import _init_db, _load_from_db, _persist_event, _delete_event, _event_from_row

_BACKOFF_BASE = 1.0  # seconds


class ReplayQueueCoreMixin:
    """
    Core operations for the dead-letter queue with event replay capability.

    Failed events are stored with error details and can be retried
    individually or in batch with exponential backoff (1s, 2s, 4s).
    After max_retries, events are marked as exhausted.

    Thread-safe with RLock. Persisted to SQLite.
    """

    def __init__(
        self,
        db_path: str | None = None,
        trigger_map: TriggerMap | None = None,  # noqa: F821
    ) -> None:
        self._lock = __import__("threading").RLock()
        self._db_path = db_path or DB_PATH  # noqa: F821
        self._events: dict[str, DeadLetterEvent] = {}  # noqa: F821
        self._trigger_map = trigger_map
        self._initialized = False
        self._init_db()
        self._load_from_db()

    # ── Lazy dependency injection ───────────────────────────────

    @property
    def trigger_map(self) -> TriggerMap:  # noqa: F821
        if self._trigger_map is None:
            self._trigger_map = get_trigger_map()  # noqa: F821
        return self._trigger_map

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

        dlq_id = f"dlq_{uuid.uuid4().hex[:12]}"  # noqa: F821
        evt = DeadLetterEvent(  # noqa: F821
            dlq_id=dlq_id,
            event_type=event_type,
            event_data=event_data,
            error=error,
            tenant_id=tenant_id,
            retry_count=0,
            max_retries=DEFAULT_MAX_RETRIES,  # noqa: F821
            last_retry_at=0.0,
            created_at=time.time(),
            status=DeadLetterStatus.PENDING,  # noqa: F821
        )

        with self._lock:
            self._events[dlq_id] = evt
        self._persist_event(evt)

        __import__("logging").getLogger("zenic_agents.events.replay_queue").info(
            "ReplayQueue: enqueued %s (event_type=%s, tenant=%s, error='%s')",
            dlq_id, event_type, tenant_id, error[:100],
        )
        return dlq_id

    # ── Dequeue ─────────────────────────────────────────────────

    def dequeue(self, dlq_id: str) -> DeadLetterEvent | None:  # noqa: F821
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
    ) -> list[DeadLetterEvent]:  # noqa: F821
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
            if evt.status not in (DeadLetterStatus.PENDING, DeadLetterStatus.RETRYING):  # noqa: F821
                continue
            if tenant_id is not None and evt.tenant_id != tenant_id:
                continue
            result.append(evt)
            if len(result) >= limit:
                break

        result.sort(key=lambda e: e.created_at)
        return result

    # ── Retry Single Event ──────────────────────────────────────

    def retry_event(self, dlq_id: str) -> RetryResult:  # noqa: F821
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
                return RetryResult(  # noqa: F821
                    success=False,
                    dlq_id=dlq_id,
                    event_type="",
                    error=f"No dead-letter event found with id {dlq_id}",
                )

            if evt.status == DeadLetterStatus.EXHAUSTED:  # noqa: F821
                return RetryResult(
                    success=False,
                    dlq_id=dlq_id,
                    event_type=evt.event_type,
                    retry_count=evt.retry_count,
                    status=evt.status,
                    error="Event is exhausted (max retries reached)",
                )

            if evt.status == DeadLetterStatus.SUCCEEDED:  # noqa: F821
                return RetryResult(
                    success=False,
                    dlq_id=dlq_id,
                    event_type=evt.event_type,
                    retry_count=evt.retry_count,
                    status=evt.status,
                    error="Event already succeeded",
                )

            # Atomic update: mark as retrying and increment count
            evt.status = DeadLetterStatus.RETRYING  # noqa: F821
            evt.retry_count += 1
            evt.last_retry_at = time.time()
            current_retry_count = evt.retry_count

        # Persist the updated state
        self._persist_event(evt)

        # Apply exponential backoff OUTSIDE the lock to avoid blocking others
        if current_retry_count > 1:
            backoff = _BACKOFF_BASE * (2 ** (current_retry_count - 1))
            time.sleep(backoff)

        # Attempt dispatch
        logger = __import__("logging").getLogger("zenic_agents.events.replay_queue")
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
                evt.status = DeadLetterStatus.SUCCEEDED  # noqa: F821
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
            if evt.retry_count >= evt.max_retries:
                with self._lock:
                    evt.status = DeadLetterStatus.EXHAUSTED  # noqa: F821
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
                    evt.status = DeadLetterStatus.PENDING  # noqa: F821
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
    ) -> BatchRetryResult:  # noqa: F821
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

        result = BatchRetryResult(total_attempted=len(candidates))  # noqa: F821

        for evt in candidates:
            rr = self.retry_event(evt.dlq_id)
            result.details.append(rr)
            if rr.success:
                result.succeeded += 1
            else:
                result.failed += 1
                if rr.status == DeadLetterStatus.EXHAUSTED:  # noqa: F821
                    result.exhausted += 1

        __import__("logging").getLogger("zenic_agents.events.replay_queue").info(
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
    ) -> BatchRetryResult:  # noqa: F821
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
                and evt.status in (DeadLetterStatus.PENDING, DeadLetterStatus.RETRYING)  # noqa: F821
                and (tenant_id is None or evt.tenant_id == tenant_id)
            ]

        candidates.sort(key=lambda e: e.created_at)
        result = BatchRetryResult(total_attempted=len(candidates))  # noqa: F821

        for evt in candidates:
            rr = self.retry_event(evt.dlq_id)
            result.details.append(rr)
            if rr.success:
                result.succeeded += 1
            else:
                result.failed += 1
                if rr.status == DeadLetterStatus.EXHAUSTED:  # noqa: F821
                    result.exhausted += 1

        __import__("logging").getLogger("zenic_agents.events.replay_queue").info(
            "ReplayQueue: replay_since(ts=%.1f, tenant=%s) — "
            "attempted=%d, succeeded=%d, failed=%d, exhausted=%d",
            since_timestamp, tenant_id,
            result.total_attempted, result.succeeded,
            result.failed, result.exhausted,
        )
        return result
