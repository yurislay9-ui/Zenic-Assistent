"""
ZENIC-AGENTS — Shared Memory Bus: Main Facade.

Ultra-fast inter-agent communication bus that composes all bus
sub-components (RingBuffer, AgentMailbox, SharedState,
PersistenceLayer, BusMetrics) into a unified API.
"""

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .mailbox import AgentMailbox
from .metrics import BusMetrics
from .persistence import PersistenceLayer
from .ring_buffer import RingBuffer
from .shared_state import SharedState
from .types import (
    BusMessage,
    MessageType,
    Priority,
    _DEFAULT_RING_SIZE,
    _FLUSH_INTERVAL_S,
)

logger = logging.getLogger(__name__)


class SharedMemoryBus:
    """Ultra-fast inter-agent communication bus.

    Combines in-memory ring buffer, SQLite WAL persistence, zero-copy
    memoryview, and per-agent write locks for sub-0.1 ms data transfer
    across 42+ agents with tenant isolation.
    """

    def __init__(self, db_path: Optional[str] = None,
                 ring_size: int = _DEFAULT_RING_SIZE,
                 tenant_id: str = "default") -> None:
        self._tenant_id = tenant_id
        self._db_path = db_path or "shared_bus.sqlite"

        # Core components
        self._ring = RingBuffer(ring_size=ring_size)
        self._state = SharedState()
        self._metrics = BusMetrics()
        self._persistence = PersistenceLayer(self._db_path)

        # Agent mailboxes: agent_id → AgentMailbox
        self._mailboxes: Dict[str, AgentMailbox] = {}
        self._mailboxes_lock = threading.Lock()

        # Registered agents for broadcast
        self._registered_agents: Dict[str, str] = {}  # agent_id → tenant_id
        self._agents_lock = threading.Lock()

        # Background flush thread
        self._stop_event = threading.Event()
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            name="SharedMemoryBus-Flush",
            daemon=True,
        )
        self._flush_thread.start()

        # TTL reaper thread (runs every 5 s)
        self._reaper_thread = threading.Thread(
            target=self._reaper_loop,
            name="SharedMemoryBus-Reaper",
            daemon=True,
        )
        self._reaper_thread.start()

        logger.info(
            "SharedMemoryBus initialised: db=%s ring=%d slots tenant=%s",
            self._db_path, ring_size, tenant_id,
        )

    # ── Mailbox API ──

    def send(self, sender: str, recipient: str, payload: Any,
             msg_type: MessageType = MessageType.DATA,
             priority: Priority = Priority.NORMAL,
             correlation_id: str = "",
             ttl_seconds: float = 300.0) -> bool:
        """Send a message to an agent's mailbox.

        O(1) in-memory delivery; async SQLite flush. Returns True.
        """
        start = time.monotonic()
        msg = BusMessage(
            sender=sender,
            recipient=recipient,
            msg_type=msg_type,
            priority=priority,
            payload=payload,
            tenant_id=self._tenant_id,
            ttl_seconds=ttl_seconds,
            correlation_id=correlation_id,
        )

        mailbox = self._get_or_create_mailbox(recipient)
        mailbox.push(msg)

        # Async persistence
        self._persistence.enqueue_message(msg)

        latency_us = (time.monotonic() - start) * 1_000_000
        self._metrics.record_send(sender, latency_us)
        return True

    def receive(self, agent_id: str, timeout_ms: float = 0) -> Optional[BusMessage]:
        """Non-blocking (or timed) receive from agent's mailbox.

        Returns the highest-priority message first. Uses a while-loop
        to discard expired TTL messages, preventing stack overflow.
        """
        mailbox = self._get_or_create_mailbox(agent_id)
        max_discards = 1000  # Safety limit to prevent infinite loops
        discards = 0
        while discards < max_discards:
            msg = mailbox.pop(timeout_ms=timeout_ms if discards == 0 else 0)
            if msg is None:
                return None
            # Check TTL — discard expired messages
            if msg.ttl_seconds > 0:
                age = time.monotonic() - msg.timestamp
                if age > msg.ttl_seconds:
                    discards += 1
                    continue  # Discard expired and try next
            self._metrics.record_receive(agent_id)
            return msg
        logger.warning("SharedMemoryBus.receive: Exceeded max TTL discards (%d) for agent %s",
                       max_discards, agent_id)
        return None

    def broadcast(self, sender: str, payload: Any,
                  msg_type: MessageType = MessageType.DATA,
                  priority: Priority = Priority.NORMAL) -> int:
        """Broadcast a message to all registered agents.

        Returns number of agents that received the message.
        """
        with self._agents_lock:
            targets = list(self._registered_agents.keys())

        count = 0
        for agent_id in targets:
            if agent_id == sender:
                continue
            if self.send(sender, agent_id, payload, msg_type, priority):
                count += 1
        return count

    def register_agent(self, agent_id: str, tenant_id: Optional[str] = None) -> None:
        """Register an agent for broadcast delivery."""
        tid = tenant_id or self._tenant_id
        with self._agents_lock:
            self._registered_agents[agent_id] = tid
        self._get_or_create_mailbox(agent_id)
        logger.debug("Agent %s registered (tenant=%s)", agent_id, tid)

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from broadcast delivery."""
        with self._agents_lock:
            self._registered_agents.pop(agent_id, None)
        with self._mailboxes_lock:
            self._mailboxes.pop(agent_id, None)

    # ── Shared State API ──

    def set_state(self, namespace: str, key: str, value: Any,
                  ttl: float = 0) -> None:
        """Set a value in shared state. O(1) in-memory, async flush."""
        self._state.set(namespace, key, value, ttl=ttl, tenant_id=self._tenant_id)
        self._persistence.enqueue_state((
            namespace, key,
            json.dumps(value, default=str),
            self._tenant_id,
            time.monotonic(),
            ttl,
        ))

    def get_state(self, namespace: str, key: str,
                  default: Any = None) -> Any:
        """Get a value from shared state. O(1) in-memory lookup."""
        return self._state.get(namespace, key, default=default,
                               tenant_id=self._tenant_id)

    def get_and_set(self, namespace: str, key: str, value: Any) -> Any:
        """Atomic get-and-set. Returns the previous value."""
        old = self._state.get_and_set(namespace, key, value,
                                       tenant_id=self._tenant_id)
        self._persistence.enqueue_state((
            namespace, key,
            json.dumps(value, default=str),
            self._tenant_id,
            time.monotonic(),
            0,
        ))
        return old

    def delete_state(self, namespace: str, key: str) -> None:
        """Delete a key from shared state."""
        self._state.delete(namespace, key, tenant_id=self._tenant_id)

    def list_keys(self, namespace: str, prefix: str = "") -> List[str]:
        """List keys in a namespace with optional prefix filter."""
        return self._state.list_keys(namespace, prefix=prefix,
                                      tenant_id=self._tenant_id)

    def register_state_callback(self, namespace: str,
                                callback: Callable[[str, str, Any], None]) -> None:
        """Register a callback for state changes in a namespace.

        Use namespace="*" to watch all namespaces.
        """
        self._state.register_callback(namespace, callback)

    # ── Ring Buffer API ──

    def write_ring(self, data: bytes, tenant_id: Optional[str] = None) -> int:
        """Write data to the ring buffer. Returns absolute slot index. O(1)."""
        tid = tenant_id or self._tenant_id
        idx = self._ring.write(data, tenant_id=tid)
        return idx

    def read_ring(self, slot_index: int) -> Optional[bytes]:
        """Read data from a ring buffer slot. O(1)."""
        return self._ring.read(slot_index)

    def read_ring_zero_copy(self, slot_index: int) -> Optional[memoryview]:
        """Zero-copy read via memoryview. Caller must not modify the view."""
        return self._ring.read_memoryview(slot_index)

    # ── Persistence ──

    def flush(self) -> None:
        """Force flush all pending writes to SQLite."""
        for slot_idx, blob, tenant_hint, ts in self._ring.snapshot_dirty_slots():
            tid = tenant_hint or self._tenant_id
            self._persistence.enqueue_ring((slot_idx, blob, tid, ts))
        self._persistence.flush()
        self._metrics.record_flush()

    def checkpoint(self) -> None:
        """Run WAL checkpoint to truncate the WAL file."""
        self._persistence.checkpoint()

    # ── Metrics ──

    def metrics(self) -> Dict[str, Any]:
        """Get bus performance metrics snapshot."""
        return self._metrics.snapshot(buffer_utilization=self._ring.utilization)

    # ── Lifecycle ──

    def close(self) -> None:
        """Flush pending data, stop background threads, and close resources."""
        logger.info("SharedMemoryBus shutting down")
        self._stop_event.set()
        self.flush()
        self._persistence.close()
        self._flush_thread.join(timeout=2.0)
        self._reaper_thread.join(timeout=2.0)
        logger.info("SharedMemoryBus closed")

    def purge_tenant(self, tenant_id: str) -> int:
        """Remove all data (in-memory + persisted) for a tenant.

        Returns the number of database rows deleted.
        """
        with self._mailboxes_lock:
            with self._agents_lock:
                to_remove = [
                    aid for aid, tid in self._registered_agents.items()
                    if tid == tenant_id
                ]
                for aid in to_remove:
                    self._registered_agents.pop(aid, None)
                    self._mailboxes.pop(aid, None)
        return self._persistence.purge_tenant(tenant_id)

    # ── Internals ──

    def _get_or_create_mailbox(self, agent_id: str) -> AgentMailbox:
        """Return the mailbox for *agent_id*, creating one if needed."""
        with self._mailboxes_lock:
            if agent_id not in self._mailboxes:
                self._mailboxes[agent_id] = AgentMailbox(agent_id)
            return self._mailboxes[agent_id]

    def _flush_loop(self) -> None:
        """Background thread that flushes pending data every 50 ms."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=_FLUSH_INTERVAL_S)
            if self._stop_event.is_set():
                break
            try:
                self.flush()
            except Exception:
                logger.exception("Flush loop error")

    def _reaper_loop(self) -> None:
        """Background thread that purges expired state entries every 5 s."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=5.0)
            if self._stop_event.is_set():
                break
            try:
                purged = self._state.purge_expired()
                if purged > 0:
                    logger.debug("Reaper purged %d expired state entries", purged)
            except Exception:
                logger.exception("Reaper loop error")
