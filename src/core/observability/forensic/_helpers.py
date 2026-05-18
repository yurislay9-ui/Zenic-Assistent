"""
forensic._helpers — Retry helper and utility functions for the forensic engine.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Retry constants ──────────────────────────────────────────
RETRY_MAX_ATTEMPTS: int = 3
RETRY_BASE_DELAY: float = 1.0  # 1 second base


def retry(fn: Any, label: str = "forensic_db_op") -> Any:
    """Execute *fn* with exponential backoff (3 retries, base 1 s)."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < RETRY_MAX_ATTEMPTS:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.debug(
                    "%s error (attempt %d/%d): %s — retrying in %.2fs",
                    label, attempt, RETRY_MAX_ATTEMPTS, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "%s failed after %d attempts: %s",
                    label, RETRY_MAX_ATTEMPTS, exc,
                )
    raise last_exc  # type: ignore[misc]


@staticmethod
def verify_local_chain(ledger_rows: List[Dict[str, Any]]) -> bool:
    """Quick chain check for the ledger rows returned by a forensic query."""
    if not ledger_rows:
        return True
    # Group by file_path
    file_groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in ledger_rows:
        fp = r.get("file_path", "__unknown__")
        file_groups.setdefault(fp, []).append(r)

    for group in file_groups.values():
        # Sorted by id ascending
        sorted_group = sorted(group, key=lambda r: r.get("id", 0))
        for i, row in enumerate(sorted_group):
            if row.get("parent_hash") == "GENESIS":
                continue
            if i == 0:
                # First entry with non-GENESIS parent — need broader context
                continue
            if row["parent_hash"] != sorted_group[i - 1]["hash_sha256"]:
                return False
    return True


@staticmethod
def compute_merkle_root(hashes: List[str]) -> str:
    """Compute a Merkle root hash from a list of leaf hashes.

    Delegates to the Rust native extension when available for
    BLAKE3-based Merkle root computation. Falls back to SHA-256
    pure Python when the extension is not compiled.
    """
    import hashlib as _hashlib

    from src.core.native import HAS_NATIVE as _HAS_NATIVE

    if not hashes:
        return _hashlib.sha256(b"empty").hexdigest()
    if len(hashes) == 1:
        return hashes[0]

    if _HAS_NATIVE:
        try:
            from src.core.native import merkle_root as _native_merkle_root_fn
            return _native_merkle_root_fn([h.encode() for h in hashes])
        except Exception:
            pass  # Fall through to pure Python

    working = list(hashes)
    while len(working) > 1:
        next_level: List[str] = []
        for i in range(0, len(working), 2):
            left = working[i]
            right = working[i + 1] if i + 1 < len(working) else left
            combined = _hashlib.sha256((left + right).encode()).hexdigest()
            next_level.append(combined)
        working = next_level
    return working[0]


@staticmethod
def build_merkle_proofs(
    ledger_entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build merkle inclusion proofs for each ledger entry."""
    proofs: List[Dict[str, Any]] = []
    if not ledger_entries:
        return proofs

    # Group by file_path for chain-based proofs
    file_groups: Dict[str, List[Dict[str, Any]]] = {}
    for entry in ledger_entries:
        fp = entry.get("file_path", "__unknown__")
        file_groups.setdefault(fp, []).append(entry)

    for fp, group in file_groups.items():
        sorted_group = sorted(group, key=lambda r: r.get("id", 0))
        all_hashes = [r["hash_sha256"] for r in sorted_group]

        root = compute_merkle_root(all_hashes)

        for entry in sorted_group:
            proofs.append({
                "file_path": fp,
                "entry_id": entry.get("id"),
                "hash_sha256": entry.get("hash_sha256", ""),
                "parent_hash": entry.get("parent_hash", ""),
                "operation": entry.get("operation", ""),
                "merkle_root": root,
                "sibling_hashes": [
                    r["hash_sha256"]
                    for r in sorted_group
                    if r.get("id") != entry.get("id")
                ],
            })

    return proofs
