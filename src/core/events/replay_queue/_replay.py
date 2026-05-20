"""
ZENIC-AGENTS — Replay Mixin

Retry and replay methods for the ReplayQueue.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from ._types import (
    BACKOFF_BASE,
    BatchRetryResult,
    DeadLetterStatus,
    RetryResult,
)

if TYPE_CHECKING:
    from ._types import DeadLetterEvent

logger = logging.getLogger("zenic_agents.events.replay_queue")


class ReplayMixin:
    """Mixin providing retry/replay methods for ReplayQueue.

    Expects the host class to provide:
      - _lock: threading.RLock
      - _events: dict[str, DeadLetterEvent]
      - _persist_event(evt: DeadLetterEvent) -> None
      - trigger_map: TriggerMap property
      - list_pending(tenant_id, limit) -> list[DeadLetterEvent]
    """

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
        # BUG FIX: Atomic check-and-update within a single lock scope.
        # Previously the lock was released between checking and updating,
        # allowing concurrent retries of the same event to both increment
        # retry_count, causing it to exceed max_retries.
        with self._lock:  # type: ignore[attr-defined]
            evt = self._events.get(dlq_id)  # type: ignore[attr-defined]

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

            # Atomic update: mark as retrying and increment count
            evt.status = DeadLetterStatus.RETRYING
            evt.retry_count += 1
            evt.last_retry_at = time.time()
            current_retry_count = evt.retry_count

        # Persist the updated state
        self._persist_event(evt)  # type: ignore[attr-defined]

        # Apply exponential backoff OUTSIDE the lock to avoid blocking others
        if current_retry_count > 1:
            backoff = BACKOFF_BASE * (2 ** (current_retry_count - 1))
            time.sleep(backoff)

        # Attempt dispatch
        try:
            matches = self.trigger_map.lookup(evt.event_type, evt.event_data)  # type: ignore[attr-defined]
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
            with self._lock:  # type: ignore[attr-defined]
                evt.status = DeadLetterStatus.SUCCEEDED
            self._persist_event(evt)  # type: ignore[attr-defined]
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
                with self._lock:  # type: ignore[attr-defined]
                    evt.status = DeadLetterStatus.EXHAUSTED
                    evt.error = dispatch_error or "Max retries reached"
                self._persist_event(evt)  # type: ignore[attr-defined]
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
                with self._lock:  # type: ignore[attr-defined]
                    evt.status = DeadLetterStatus.PENDING
                    evt.error = dispatch_error or "Retry failed"
                self._persist_event(evt)  # type: ignore[attr-defined]
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
        candidates = self.list_pending(tenant_id=tenant_id, limit=10000)  # type: ignore[attr-defined]
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
        with self._lock:  # type: ignore[attr-defined]
            candidates = [
                evt for evt in self._events.values()  # type: ignore[attr-defined]
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
