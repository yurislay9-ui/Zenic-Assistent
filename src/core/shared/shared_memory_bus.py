"""
ZENIC-AGENTS — Shared Memory Bus for Ultra-Fast Inter-Agent Communication.

This module implements the core inter-agent communication layer that replaces
slow Python dict passing with a zero-copy shared memory architecture backed
by SQLite WAL-mode for persistence.

Architecture:
    ┌──────────────────────────────────────────────────────────────┐
    │                     SharedMemoryBus                          │
    │                                                              │
    │  ┌────────────┐  ┌────────────┐  ┌───────────────────────┐  │
    │  │ RingBuffer │  │  AgentMail  │  │     SharedState       │  │
    │  │ 1024×4KB   │  │  boxes     │  │  KV + ReadWriteLock   │  │
    │  │ zero-copy  │  │  priority  │  │  TTL + callbacks      │  │
    │  └─────┬──────┘  └─────┬──────┘  └──────────┬────────────┘  │
    │        │               │                     │               │
    │        └───────────────┼─────────────────────┘               │
    │                        │                                     │
    │              ┌─────────▼──────────┐                          │
    │              │ PersistenceLayer   │                          │
    │              │ SQLite WAL-mode    │                          │
    │              │ Batch 50ms/100 ops │                          │
    │              └────────────────────┘                          │
    │                                                              │
    │              ┌────────────────────┐                          │
    │              │   BusMetrics       │                          │
    │              │   Lock-free cnts   │                          │
    │              └────────────────────┘                          │
    └──────────────────────────────────────────────────────────────┘

Performance targets:
    - send()        < 0.05ms  (in-memory deque + async SQLite)
    - receive()     < 0.05ms  (in-memory heapq pop)
    - set_state()   < 0.05ms  (in-memory dict + async SQLite)
    - get_state()   < 0.02ms  (in-memory dict lookup)
    - write_ring()  < 0.01ms  (pre-allocated buffer + atomic index)
    - read_ring()   < 0.01ms  (memoryview slice)
    - broadcast()   < 0.5ms   (O(N) fan-out to N mailboxes)

Thread safety:
    - Mailbox:    per-mailbox Lock (not global)
    - SharedState: ReadWriteLock (concurrent reads, exclusive writes)
    - RingBuffer:  atomic index counter, per-slot write lock
    - SQLite:     WAL mode (concurrent reads, single writer)
    - Metrics:    simple counters (minor races acceptable)

This module is a thin facade that re-exports all public symbols from
the ``bus_parts`` sub-package.  All implementation lives in:
    - bus_parts.types         — MessageType, Priority, BusMessage, constants
    - bus_parts.ring_buffer   — RingBuffer
    - bus_parts.mailbox       — AgentMailbox
    - bus_parts.shared_state  — SharedState
    - bus_parts.persistence   — PersistenceLayer
    - bus_parts.metrics       — BusMetrics
    - bus_parts.bus           — SharedMemoryBus (main facade)
"""

# Re-export all public symbols from bus_parts for backward compatibility.
from src.core.shared.bus_parts import (  # noqa: F401
    AgentMailbox,
    BusMessage,
    BusMetrics,
    MessageType,
    PersistenceLayer,
    Priority,
    RingBuffer,
    SharedMemoryBus,
    SharedState,
)

__all__ = [
    # Enums
    "MessageType",
    "Priority",
    # Data classes
    "BusMessage",
    # Components
    "RingBuffer",
    "AgentMailbox",
    "SharedState",
    "PersistenceLayer",
    "BusMetrics",
    # Main class
    "SharedMemoryBus",
]
