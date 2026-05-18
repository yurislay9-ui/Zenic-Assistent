"""
ZENIC-AGENTS — Forensic analyzer.

Chain verification, merkle proof building, and merkle root computation
used by the ForensicEngine.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List

from src.core.native import (
    HAS_NATIVE as _HAS_NATIVE,
)

from ._types import ChainVerificationResult

logger = logging.getLogger(__name__)


# ── Local chain verification ─────────────────────────────────

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


# ── Full chain verification ──────────────────────────────────

def verify_chain_entries(
    ledger_rows: List[Dict[str, Any]],
    tenant_id: str,
) -> ChainVerificationResult:
    """Verify Merkle chain integrity for all ledger entries of a tenant.

    Walks the ledger chronologically and checks that every entry's
    parent_hash matches the preceding entry's hash_sha256.  Breaks
    are recorded with full details.

    Args:
        ledger_rows: Pre-loaded ledger rows (list of dicts).
        tenant_id: Tenant whose ledger chain is being verified.

    Returns:
        ChainVerificationResult with validity status and break details.
    """
    broken_links: List[Dict[str, Any]] = []
    valid_count = 0

    # Build a lookup: id -> row for parent resolution
    id_to_row: Dict[int, Dict[str, Any]] = {
        r["id"]: r for r in ledger_rows
    }
    # Build a lookup: hash -> row id for parent resolution
    hash_to_id: Dict[str, int] = {}
    for r in ledger_rows:
        hash_to_id[r["hash_sha256"]] = r["id"]

    # Group by file_path and verify each chain independently
    file_groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in ledger_rows:
        fp = r["file_path"]
        file_groups.setdefault(fp, []).append(r)

    for fp, group in file_groups.items():
        # group is already sorted by id ASC
        for i, row in enumerate(group):
            if row["parent_hash"] == "GENESIS":
                valid_count += 1
                continue

            # Check if parent_hash matches previous entry's hash_sha256
            expected_parent_hash = ""
            if i > 0:
                expected_parent_hash = group[i - 1]["hash_sha256"]
            else:
                # First entry for this file with a non-GENESIS parent —
                # look up the parent by hash across all entries
                expected_parent_hash = row["parent_hash"]
                if row["parent_hash"] in hash_to_id:
                    valid_count += 1
                    continue

            if row["parent_hash"] == expected_parent_hash:
                valid_count += 1
            else:
                broken_links.append({
                    "file_path": fp,
                    "entry_id": row["id"],
                    "expected_parent_hash": expected_parent_hash,
                    "actual_parent_hash": row["parent_hash"],
                    "entry_hash": row["hash_sha256"],
                    "operation": row["operation"],
                    "timestamp": row["timestamp"],
                })

    total = len(ledger_rows)
    is_valid = len(broken_links) == 0
    root_hash = ledger_rows[-1]["hash_sha256"] if ledger_rows else ""

    return ChainVerificationResult(
        tenant_id=tenant_id,
        total_entries=total,
        valid_entries=valid_count,
        broken_links=broken_links,
        is_valid=is_valid,
        root_hash=root_hash,
    )


# ── Merkle proofs ────────────────────────────────────────────

def build_merkle_proofs(
    ledger_entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build merkle inclusion proofs for each ledger entry.

    Each proof contains the entry's hash, its parent hash, and the
    sibling hashes needed to reconstruct the path to the root.
    For a simplified proof, we include the direct chain links.
    """
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
        # Collect all hashes for merkle root computation
        all_hashes = [r["hash_sha256"] for r in sorted_group]

        # Compute merkle root
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


# ── Merkle root ──────────────────────────────────────────────

def compute_merkle_root(hashes: List[str]) -> str:
    """Compute a Merkle root hash from a list of leaf hashes.

    Delegates to the Rust native extension when available for
    BLAKE3-based Merkle root computation. Falls back to SHA-256
    pure Python when the extension is not compiled.
    """
    from src.core.native import merkle_root as _native_merkle_root_fn

    if not hashes:
        return hashlib.sha256(b"empty").hexdigest()
    if len(hashes) == 1:
        return hashes[0]

    if _HAS_NATIVE:
        try:
            return _native_merkle_root_fn([h.encode() for h in hashes])
        except Exception:
            pass  # Fall through to pure Python

    working = list(hashes)
    while len(working) > 1:
        next_level: List[str] = []
        for i in range(0, len(working), 2):
            left = working[i]
            right = working[i + 1] if i + 1 < len(working) else left
            combined = hashlib.sha256((left + right).encode()).hexdigest()
            next_level.append(combined)
        working = next_level
    return working[0]
