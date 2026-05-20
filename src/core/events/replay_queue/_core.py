"""replay_queue — Core implementation (composed from mixins)."""

from __future__ import annotations

from ._mixin_core import ReplayQueueCoreMixin
from ._mixin_persistence import ReplayQueuePersistenceMixin


class ReplayQueue(ReplayQueueCoreMixin, ReplayQueuePersistenceMixin):
    """
    Dead-letter queue with event replay capability.

    Failed events are stored with error details and can be retried
    individually or in batch with exponential backoff (1s, 2s, 4s).
    After max_retries, events are marked as exhausted.

    Thread-safe with RLock. Persisted to SQLite.
    Singleton pattern via get_replay_queue() / reset_replay_queue().
    """


__all__ = [
    "ReplayQueue",
]
