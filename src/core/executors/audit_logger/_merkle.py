"""
ZENIC-AGENTS - Executor Audit Logger: Merkle Chain

Lightweight hash chain for tamper-proof audit integrity.
"""

import hashlib
import json
import logging
import threading
from typing import Callable, List, Optional

from ._types import AuditEntry

logger = logging.getLogger(__name__)


class AuditMerkleChain:
    """Lightweight hash chain for audit integrity.

    Each entry's merkle_hash = SHA256(prev_hash + entry_data).
    Tampering with any entry invalidates all subsequent hashes.
    """

    GENESIS_HASH = "0" * 64

    def __init__(
        self,
        persist_callback: Optional[Callable[[List["AuditEntry"], str], None]] = None,
        flush_interval: int = 100,
        hash_algorithm: str = "sha256",
    ) -> None:
        self._last_hash: str = self.GENESIS_HASH
        self._lock = threading.Lock()
        self._persist_callback = persist_callback
        self._pending_entries: List = []
        self._flush_interval = flush_interval
        self._hash_algorithm = hash_algorithm
        self._hash_fn = self._init_hash_fn(hash_algorithm)

    @staticmethod
    def _init_hash_fn(algorithm: str):
        """Initialize the hash function based on algorithm name.

        Supports 'sha256' (default, Python/TS compatible) and 'blake3' (Rust compatible).
        """
        if algorithm == "blake3":
            try:
                import blake3 as _blake3
                return lambda data: _blake3.blake3(data.encode() if isinstance(data, str) else data).hexdigest()
            except ImportError:
                logger.warning(
                    "AuditMerkleChain: blake3 package not available, "
                    "falling back to SHA-256. Install 'blake3' for Rust compatibility."
                )
                return lambda data: hashlib.sha256(
                    data.encode() if isinstance(data, str) else data
                ).hexdigest()
        # Default: SHA-256 (compatible with TypeScript merkle-audit.ts)
        return lambda data: hashlib.sha256(
            data.encode() if isinstance(data, str) else data
        ).hexdigest()

    def compute_hash(self, entry: AuditEntry) -> str:
        """Compute merkle hash for an entry."""
        entry_data = json.dumps({
            "action_type": entry.action_type,
            "operation": entry.operation,
            "executor_class": entry.executor_class,
            "verdict": entry.verdict,
            "success": entry.success,
            "timestamp": entry.timestamp,
            "prev_hash": self._last_hash,
        }, sort_keys=True)
        return self._hash_fn(entry_data.encode())

    def seal(self, entry: AuditEntry) -> str:
        """Compute and assign merkle hash to entry, advance chain.

        If a persist_callback is configured, entries are flushed
        periodically (every flush_interval entries) to persistent storage.
        """
        with self._lock:
            h = self.compute_hash(entry)
            entry.prev_hash = self._last_hash
            entry.merkle_hash = h
            self._last_hash = h
            self._pending_entries.append(entry)

            if len(self._pending_entries) >= self._flush_interval:
                self._flush()

            return h

    def _flush(self) -> None:
        """Flush pending entries to persistent storage."""
        if self._persist_callback and self._pending_entries:
            try:
                self._persist_callback(list(self._pending_entries), self._last_hash)
                self._pending_entries.clear()
            except Exception as exc:
                logger.error("AuditMerkleChain: Flush failed: %s", exc)
                # Don't clear — retry on next flush

    def flush_now(self) -> None:
        """Force flush all pending entries (for graceful shutdown)."""
        with self._lock:
            self._flush()

    def verify(self, entries: List[AuditEntry]) -> bool:
        """Verify integrity of a list of audit entries."""
        prev = self.GENESIS_HASH
        for entry in entries:
            expected = self._hash_fn(json.dumps({
                "action_type": entry.action_type,
                "operation": entry.operation,
                "executor_class": entry.executor_class,
                "verdict": entry.verdict,
                "success": entry.success,
                "timestamp": entry.timestamp,
                "prev_hash": prev,
            }, sort_keys=True).encode())
            if entry.merkle_hash != expected:
                logger.error(
                    "AuditMerkleChain: Tampering detected at entry %s. "
                    "Expected hash=%s, got=%s",
                    entry.entry_id, expected[:16], entry.merkle_hash[:16],
                )
                return False
            prev = entry.merkle_hash
        return True

    @property
    def last_hash(self) -> str:
        return self._last_hash
