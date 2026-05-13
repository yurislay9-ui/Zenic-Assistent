"""
ZENIC-AGENTS — Shared Memory Bus Sub-Modules.

Re-exports all public symbols from the bus_parts sub-modules so that
``from src.core.shared.bus_parts import SharedMemoryBus`` works as
expected.
"""

from .bus import SharedMemoryBus
from .mailbox import AgentMailbox
from .metrics import BusMetrics
from .persistence import PersistenceLayer
from .ring_buffer import RingBuffer
from .shared_state import SharedState
from .types import BusMessage, MessageType, Priority

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
