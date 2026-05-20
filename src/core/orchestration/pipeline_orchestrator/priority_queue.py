"""
Priority Queue — Priority-based step queue for pipeline orchestration.

Provides a priority queue implementation optimized for pipeline step
scheduling, with support for dynamic priority updates, step
cancellation, and batch operations.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
No external dependencies beyond Python stdlib.
"""

from __future__ import annotations

import heapq
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

__all__ = [
    "PrioritizedItem",
    "PriorityQueue",
]


# ──────────────────────────────────────────────────────────────
#  DATA CONTRACTS
# ──────────────────────────────────────────────────────────────

@dataclass
class PrioritizedItem:
    """
    An item in the priority queue with an associated priority.

    Lower priority values are dequeued first (min-heap semantics).

    Attributes:
        item_id: Unique identifier for the item.
        data: The payload carried by this item.
        priority: Scheduling priority (lower = higher urgency).
        category: Optional category for filtering.
        metadata: Additional metadata.
    """
    item_id: str
    data: Any = None
    priority: float = 0.0
    category: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.item_id:
            self.item_id = f"item-{uuid.uuid4().hex[:8]}"

    def __lt__(self, other: PrioritizedItem) -> bool:
        """Compare by priority for heap ordering."""
        if not isinstance(other, PrioritizedItem):
            return NotImplemented
        return self.priority < other.priority

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PrioritizedItem):
            return NotImplemented
        return self.item_id == other.item_id

    def __hash__(self) -> int:
        return hash(self.item_id)


# ──────────────────────────────────────────────────────────────
#  PRIORITY QUEUE
# ──────────────────────────────────────────────────────────────

class PriorityQueue:
    """
    Priority-based queue for pipeline step scheduling.

    Uses a min-heap internally, so items with lower priority values
    are dequeued first. Supports dynamic priority updates, cancellation,
    and category-based filtering.

    Usage::

        queue = PriorityQueue()
        queue.enqueue(PrioritizedItem("step_1", priority=2.0))
        queue.enqueue(PrioritizedItem("step_2", priority=1.0))
        queue.enqueue(PrioritizedItem("step_3", priority=3.0))

        item = queue.dequeue()  # step_2 (priority=1.0)

    Thread Safety:
        This class is NOT thread-safe. External synchronization is required.
    """

    def __init__(self) -> None:
        self._heap: List[PrioritizedItem] = []
        self._items: Dict[str, PrioritizedItem] = {}
        self._cancelled: Set[str] = set()
        self._total_enqueued: int = 0
        self._total_dequeued: int = 0

    # ── Enqueue / Dequeue ────────────────────────────────────

    def enqueue(self, item: PrioritizedItem) -> None:
        """
        Add an item to the priority queue.

        Args:
            item: The PrioritizedItem to enqueue.

        Raises:
            ValueError: If an item with the same item_id already exists.
        """
        if item.item_id in self._items:
            raise ValueError(f"Item '{item.item_id}' already exists in the queue")
        self._items[item.item_id] = item
        heapq.heappush(self._heap, item)
        self._total_enqueued += 1
        logger.debug(
            "PriorityQueue: Enqueued '%s' (priority=%.1f, category='%s')",
            item.item_id, item.priority, item.category,
        )

    def dequeue(self) -> Optional[PrioritizedItem]:
        """
        Remove and return the highest-priority (lowest value) item.

        Skips cancelled items automatically.

        Returns:
            The PrioritizedItem, or None if the queue is empty.
        """
        while self._heap:
            item = heapq.heappop(self._heap)
            # Skip cancelled items
            if item.item_id in self._cancelled:
                self._cancelled.discard(item.item_id)
                self._items.pop(item.item_id, None)
                continue
            # Skip stale entries (item was updated)
            if item.item_id in self._items and self._items[item.item_id] is item:
                del self._items[item.item_id]
                self._total_dequeued += 1
                return item
            elif item.item_id not in self._items:
                # Item was removed, skip
                continue

        return None

    def peek(self) -> Optional[PrioritizedItem]:
        """
        Look at the highest-priority item without removing it.

        Returns:
            The PrioritizedItem, or None if the queue is empty.
        """
        # Clean up cancelled/stale entries at the front
        while self._heap:
            item = self._heap[0]
            if item.item_id in self._cancelled:
                heapq.heappop(self._heap)
                self._cancelled.discard(item.item_id)
                self._items.pop(item.item_id, None)
                continue
            if item.item_id not in self._items:
                heapq.heappop(self._heap)
                continue
            if self._items[item.item_id] is not item:
                heapq.heappop(self._heap)
                continue
            return item
        return None

    # ── Priority Updates ─────────────────────────────────────

    def update_priority(self, item_id: str, new_priority: float) -> bool:
        """
        Update the priority of an existing item.

        This works by inserting a new entry with the updated priority.
        The old entry becomes stale and will be skipped on dequeue.

        Args:
            item_id: The item to update.
            new_priority: The new priority value.

        Returns:
            True if the item was found and updated, False otherwise.
        """
        if item_id not in self._items or item_id in self._cancelled:
            return False

        old_item = self._items[item_id]
        updated = PrioritizedItem(
            item_id=item_id,
            data=old_item.data,
            priority=new_priority,
            category=old_item.category,
            metadata=old_item.metadata,
        )
        # Replace in dict and push new entry (old entry becomes stale)
        self._items[item_id] = updated
        heapq.heappush(self._heap, updated)
        logger.debug(
            "PriorityQueue: Updated '%s' priority %.1f -> %.1f",
            item_id, old_item.priority, new_priority,
        )
        return True

    # ── Cancellation ─────────────────────────────────────────

    def cancel(self, item_id: str) -> bool:
        """
        Cancel an item so it won't be dequeued.

        Args:
            item_id: The item to cancel.

        Returns:
            True if the item was found and cancelled.
        """
        if item_id in self._items and item_id not in self._cancelled:
            self._cancelled.add(item_id)
            logger.debug("PriorityQueue: Cancelled '%s'", item_id)
            return True
        return False

    def is_cancelled(self, item_id: str) -> bool:
        """Check if an item has been cancelled."""
        return item_id in self._cancelled

    # ── Batch Operations ─────────────────────────────────────

    def enqueue_batch(self, items: List[PrioritizedItem]) -> None:
        """
        Add multiple items to the queue.

        Args:
            items: List of PrioritizedItem instances.
        """
        for item in items:
            self.enqueue(item)

    def dequeue_batch(self, max_items: int = 10) -> List[PrioritizedItem]:
        """
        Dequeue up to max_items from the queue.

        Args:
            max_items: Maximum number of items to dequeue.

        Returns:
            List of dequeued PrioritizedItem instances.
        """
        result: List[PrioritizedItem] = []
        while len(result) < max_items:
            item = self.dequeue()
            if item is None:
                break
            result.append(item)
        return result

    def dequeue_by_category(self, category: str, max_items: int = 10) -> List[PrioritizedItem]:
        """
        Dequeue items matching a specific category.

        Note: This scans the heap and is O(n). For frequent category-based
        queries, consider using separate queues per category.

        Args:
            category: The category to filter by.
            max_items: Maximum number of items to dequeue.

        Returns:
            List of matching PrioritizedItem instances.
        """
        result: List[PrioritizedItem] = []
        remaining: List[PrioritizedItem] = []

        while self._heap:
            item = heapq.heappop(self._heap)
            if item.item_id in self._cancelled:
                self._cancelled.discard(item.item_id)
                self._items.pop(item.item_id, None)
                continue
            if item.item_id not in self._items or self._items[item.item_id] is not item:
                continue
            if item.category == category and len(result) < max_items:
                del self._items[item.item_id]
                self._total_dequeued += 1
                result.append(item)
            else:
                remaining.append(item)

        # Re-push non-matching items
        for item in remaining:
            heapq.heappush(self._heap, item)

        return result

    # ── Accessors ────────────────────────────────────────────

    @property
    def size(self) -> int:
        """Number of active (non-cancelled) items in the queue."""
        return len(self._items) - len(self._cancelled)

    @property
    def is_empty(self) -> bool:
        """Whether the queue has no active items."""
        return self.size == 0

    def contains(self, item_id: str) -> bool:
        """Check if an item is in the queue (and not cancelled)."""
        return item_id in self._items and item_id not in self._cancelled

    def get_item(self, item_id: str) -> Optional[PrioritizedItem]:
        """Get an item by ID without removing it."""
        if item_id in self._items and item_id not in self._cancelled:
            return self._items[item_id]
        return None

    @property
    def categories(self) -> Set[str]:
        """Set of all categories currently in the queue."""
        return {
            item.category
            for item in self._items.values()
            if item.item_id not in self._cancelled and item.category
        }

    @property
    def stats(self) -> Dict[str, Any]:
        """Runtime statistics."""
        return {
            "size": self.size,
            "total_enqueued": self._total_enqueued,
            "total_dequeued": self._total_dequeued,
            "cancelled_count": len(self._cancelled),
            "categories": list(self.categories),
        }

    def clear(self) -> None:
        """Remove all items from the queue."""
        self._heap.clear()
        self._items.clear()
        self._cancelled.clear()

    def __len__(self) -> int:
        return self.size

    def __repr__(self) -> str:
        return f"PriorityQueue(size={self.size})"
