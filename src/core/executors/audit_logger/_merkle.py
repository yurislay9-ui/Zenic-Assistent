"""
ZENIC-AGENTS - Executor Audit Logger: Merkle Chain

Lightweight hash chain for tamper-proof audit integrity.
"""

import hashlib
import json
import logging
import threading
from typing import List

from ._types import AuditEntry

logger = logging.getLogger(__name__)


class AuditMerkleChain:
    """Lightweight hash chain for audit integrity.

    Each entry's merkle_hash = SHA256(prev_hash + entry_data).
    Tampering with any entry invalidates all subsequent hashes.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self) -> None:
        self._last_hash: str = self.GENESIS_HASH
        self._lock = threading.Lock()

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
        return hashlib.sha256(entry_data.encode()).hexdigest()

    def seal(self, entry: AuditEntry) -> str:
        """Compute and assign merkle hash to entry, advance chain."""
        with self._lock:
            h = self.compute_hash(entry)
            entry.prev_hash = self._last_hash
            entry.merkle_hash = h
            self._last_hash = h
            return h

    def verify(self, entries: List[AuditEntry]) -> bool:
        """Verify integrity of a list of audit entries."""
        prev = self.GENESIS_HASH
        for entry in entries:
            expected = hashlib.sha256(json.dumps({
                "action_type": entry.action_type,
                "operation": entry.operation,
                "executor_class": entry.executor_class,
                "verdict": entry.verdict,
                "success": entry.success,
                "timestamp": entry.timestamp,
                "prev_hash": prev,
            }, sort_keys=True).encode()).hexdigest()
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
