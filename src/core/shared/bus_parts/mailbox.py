"""
ZENIC-AGENTS — Shared Memory Bus: Agent Mailbox.

Per-agent priority message queue backed by a heap. Messages are
ordered by (priority, timestamp) so the highest-priority message
is always dequeued first.
"""

import heapq
import logging
import threading
import time
from typing import List, Optional, Tuple

from .types import BusMessage, _MAX_MAILBOX_DEPTH

logger = logging.getLogger(__name__)


class AgentMailbox:
    """Per-agent priority message queue.

    Messages are stored in a heap ordered by ``(priority, timestamp)`` so
    that the highest-priority (lowest numeric) message is always dequeued
    first. Non-blocking reads are O(log N) via ``heapq``.

    When the mailbox exceeds *_MAX_MAILBOX_DEPTH*, the lowest-priority
    (highest numeric value) message is evicted (LRU by priority).

    Args:
        agent_id: The owning agent's identifier.
    """

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._lock = threading.Lock()
        # Heap of (priority, timestamp, sequence, BusMessage)
        self._heap: List[Tuple[int, float, int, BusMessage]] = []
        self._seq = 0  # Tie-breaker to maintain FIFO within same priority
        self._not_empty = threading.Condition(self._lock)

    # ── Enqueue ──

    def push(self, msg: BusMessage) -> None:
        """Push a message into the mailbox."""
        with self._not_empty:
            if len(self._heap) >= _MAX_MAILBOX_DEPTH:
                self._evict_one()
            self._seq += 1
            heapq.heappush(
                self._heap,
                (int(msg.priority), msg.timestamp, self._seq, msg),
            )
            self._not_empty.notify()

    def _evict_one(self) -> None:
        """Evict the lowest-priority (highest numeric) message."""
        if not self._heap:
            return
        # Find max-priority item (highest numeric value = lowest priority)
        max_idx = max(range(len(self._heap)),
                      key=lambda i: self._heap[i][0])
        evicted = self._heap.pop(max_idx)
        if evicted is not None:
            heapq.heapify(self._heap)
            logger.debug(
                "Mailbox %s evicted message from %s (priority=%d)",
                self.agent_id, evicted[3].sender, evicted[0],
            )

    # ── Dequeue ──

    def pop(self, timeout_ms: float = 0) -> Optional[BusMessage]:
        """Non-blocking (or timed) pop of the highest-priority message.

        Args:
            timeout_ms: Maximum time to wait in milliseconds.
                0 = non-blocking (default).

        Returns:
            The highest-priority :class:`BusMessage`, or ``None``.
        """
        deadline = time.monotonic() + timeout_ms / 1000.0
        with self._not_empty:
            while not self._heap:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                if not self._not_empty.wait(timeout=remaining):
                    return None
            _, _, _, msg = heapq.heappop(self._heap)
            return msg

    # ── Introspection ──

    @property
    def depth(self) -> int:
        """Current number of messages in the mailbox."""
        with self._lock:
            return len(self._heap)

    @property
    def is_empty(self) -> bool:
        """Whether the mailbox has no messages."""
        with self._lock:
            return len(self._heap) == 0

    def peek_all(self) -> List[BusMessage]:
        """Return a snapshot of all messages without removing them."""
        with self._lock:
            return [item[3] for item in sorted(self._heap)]
