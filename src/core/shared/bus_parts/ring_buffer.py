"""
ZENIC-AGENTS — Shared Memory Bus: Ring Buffer.

Fixed-size circular buffer for hot-path data with zero-copy reads
via memoryview slices.
"""

import struct
import threading
import time
from typing import Dict, List, Optional, Tuple

from .types import (
    _DEFAULT_RING_SIZE,
    _RING_SLOT_SIZE,
    _SLOT_HEADER_FMT,
    _SLOT_HEADER_SIZE,
)


class RingBuffer:
    """Fixed-size circular buffer for hot-path data.

    Pre-allocates *ring_size* slots, each *slot_size* bytes. Writes are
    O(1) via an atomic counter; reads are O(1) by slot index. Zero-copy
    reads are provided via ``memoryview`` slices.

    Args:
        ring_size: Number of slots in the ring (default 1024).
        slot_size: Bytes per slot (default 4096).
    """

    def __init__(self, ring_size: int = _DEFAULT_RING_SIZE,
                 slot_size: int = _RING_SLOT_SIZE) -> None:
        self._ring_size = ring_size
        self._slot_size = slot_size
        # Pre-allocated flat buffer: ring_size × slot_size
        self._buffer = bytearray(ring_size * slot_size)
        self._view = memoryview(self._buffer)
        # Atomic write index (monotonically increasing)
        self._write_idx: int = 0
        self._idx_lock = threading.Lock()
        # Per-slot write locks to avoid global contention
        self._slot_locks = [threading.Lock() for _ in range(ring_size)]
        # Track which slots are occupied: slot→(timestamp, tenant_id)
        self._slot_meta: Dict[int, Tuple[float, str]] = {}

    # ── Write ──

    def write(self, data: bytes, tenant_id: str = "default") -> int:
        """Write *data* to the next available slot.

        Returns:
            The absolute slot index (wrap-aware).

        Raises:
            ValueError: If *data* exceeds slot capacity.
        """
        max_payload = self._slot_size - _SLOT_HEADER_SIZE
        if len(data) > max_payload:
            raise ValueError(
                f"Data size {len(data)} exceeds max payload {max_payload} bytes"
            )

        with self._idx_lock:
            abs_idx = self._write_idx
            self._write_idx += 1

        slot_idx = abs_idx % self._ring_size
        tenant_hash = hash(tenant_id) & 0xFFFFFFFF

        with self._slot_locks[slot_idx]:
            offset = slot_idx * self._slot_size
            # Write header
            struct.pack_into(
                _SLOT_HEADER_FMT,
                self._buffer,
                offset,
                len(data),
                tenant_hash,
            )
            # Write payload
            start = offset + _SLOT_HEADER_SIZE
            self._buffer[start:start + len(data)] = data
            self._slot_meta[slot_idx] = (time.monotonic(), tenant_id)

        return abs_idx

    # ── Read ──

    def read(self, slot_index: int) -> Optional[bytes]:
        """Read data from a slot by absolute index.

        Returns:
            The payload bytes, or ``None`` if the slot is empty / expired.
        """
        slot_idx = slot_index % self._ring_size
        offset = slot_idx * self._slot_size

        with self._slot_locks[slot_idx]:
            data_len, tenant_hash = struct.unpack_from(
                _SLOT_HEADER_FMT, self._buffer, offset
            )
            if data_len == 0:
                return None
            start = offset + _SLOT_HEADER_SIZE
            return bytes(self._view[start:start + data_len])

    def read_memoryview(self, slot_index: int) -> Optional[memoryview]:
        """Zero-copy read via memoryview slice.

        The caller **must not** modify the returned view.
        """
        slot_idx = slot_index % self._ring_size
        offset = slot_idx * self._slot_size

        with self._slot_locks[slot_idx]:
            data_len, _tenant_hash = struct.unpack_from(
                _SLOT_HEADER_FMT, self._buffer, offset
            )
            if data_len == 0:
                return None
            start = offset + _SLOT_HEADER_SIZE
            return self._view[start:start + data_len]

    # ── Introspection ──

    @property
    def utilization(self) -> float:
        """Fraction of slots currently occupied (0.0–1.0)."""
        return len(self._slot_meta) / self._ring_size if self._ring_size else 0.0

    @property
    def write_index(self) -> int:
        """Current absolute write index."""
        return self._write_idx

    def snapshot_dirty_slots(self) -> List[Tuple[int, bytes, str, float]]:
        """Return all occupied slots for persistence.

        Returns:
            List of (slot_index, data_blob, tenant_id, timestamp).
        """
        result: List[Tuple[int, bytes, str, float]] = []
        for slot_idx, (ts, tenant_id) in list(self._slot_meta.items()):
            offset = slot_idx * self._slot_size
            data_len, _ = struct.unpack_from(
                _SLOT_HEADER_FMT, self._buffer, offset
            )
            if data_len > 0:
                start = offset + _SLOT_HEADER_SIZE
                blob = bytes(self._buffer[start:start + data_len])
                result.append((slot_idx, blob, tenant_id, ts))
        return result
