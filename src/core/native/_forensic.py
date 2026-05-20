"""
native._forensic — Forensic Audit (A1) API functions.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Dict, List

from src.core.native._bindings import HAS_NATIVE

if HAS_NATIVE:
    from src.core.native._bindings import (
        _rust_forensic_hash,
        _rust_chain_hash,
        _rust_verify_merkle_chain,
        _rust_merkle_proof,
        _rust_batch_verify_chains,
    )


def forensic_hash(
    entry_id: str,
    tenant_id: str,
    event_type: str,
    description: str,
    actor: str,
    timestamp: str,
    metadata_json: str,
) -> str:
    """Generate a forensic BLAKE3 hash from audit entry fields."""
    if HAS_NATIVE:
        return _rust_forensic_hash(
            entry_id, tenant_id, event_type, description,
            actor, timestamp, metadata_json,
        )
    # Pure Python fallback
    if not entry_id:
        raise ValueError("entry_id must not be empty")
    if not tenant_id:
        raise ValueError("tenant_id must not be empty")
    payload = "|".join([
        entry_id, tenant_id, event_type, description,
        actor, timestamp, metadata_json,
    ])
    try:
        import blake3 as _blake3  # type: ignore[import-untyped]
        return _blake3.blake3(payload.encode()).hexdigest()
    except ImportError:
        return hashlib.sha256(payload.encode()).hexdigest()


def chain_hash(parent_hash: str, entry_hash: str) -> str:
    """Generate a chain hash linking an entry to its parent."""
    if HAS_NATIVE:
        return _rust_chain_hash(parent_hash, entry_hash)
    # Pure Python fallback
    if not parent_hash and not entry_hash:
        raise ValueError("at least one of parent_hash or entry_hash must be non-empty")
    combined = (parent_hash + entry_hash).encode()
    try:
        import blake3 as _blake3  # type: ignore[import-untyped]
        return _blake3.blake3(combined).hexdigest()
    except ImportError:
        return hashlib.sha256(combined).hexdigest()


def verify_merkle_chain(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verify Merkle chain integrity for a list of ledger entries."""
    if HAS_NATIVE:
        return _rust_verify_merkle_chain(entries)
    # Pure Python fallback
    if not entries:
        return {"is_valid": True, "total_entries": 0, "valid_entries": 0,
                "broken_links": [], "root_hash": ""}

    total = len(entries)
    valid_count = 0
    broken_links: List[Dict[str, Any]] = []

    # Group by file_path
    file_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in entries:
        fp = r.get("file_path", "__unknown__")
        file_groups[fp].append(r)

    for fp, group in file_groups.items():
        sorted_group = sorted(group, key=lambda r: r.get("id", 0))
        for i, row in enumerate(sorted_group):
            if row.get("parent_hash") == "GENESIS":
                valid_count += 1
                continue
            if i == 0:
                parent_hash = row.get("parent_hash", "")
                parent_exists = any(
                    e.get("hash_sha256") == parent_hash for e in entries
                )
                if parent_exists:
                    valid_count += 1
                else:
                    broken_links.append({
                        "file_path": fp, "entry_id": row.get("id"),
                        "expected_parent_hash": parent_hash,
                        "actual_parent_hash": parent_hash,
                        "entry_hash": row.get("hash_sha256", ""),
                        "operation": row.get("operation", ""),
                        "timestamp": row.get("timestamp", 0.0),
                    })
                continue
            expected = sorted_group[i - 1].get("hash_sha256", "")
            actual = row.get("parent_hash", "")
            if actual == expected:
                valid_count += 1
            else:
                broken_links.append({
                    "file_path": fp, "entry_id": row.get("id"),
                    "expected_parent_hash": expected,
                    "actual_parent_hash": actual,
                    "entry_hash": row.get("hash_sha256", ""),
                    "operation": row.get("operation", ""),
                    "timestamp": row.get("timestamp", 0.0),
                })

    root_hash = entries[-1].get("hash_sha256", "") if entries else ""
    return {
        "is_valid": len(broken_links) == 0,
        "total_entries": total,
        "valid_entries": valid_count,
        "broken_links": broken_links,
        "root_hash": root_hash,
    }


def merkle_proof(
    entry_hash: str, all_hashes: List[str],
) -> Dict[str, Any]:
    """Generate a Merkle inclusion proof for an entry."""
    if HAS_NATIVE:
        return _rust_merkle_proof(entry_hash, all_hashes)
    # Pure Python fallback
    if not all_hashes:
        raise ValueError("all_hashes must not be empty")

    try:
        idx = all_hashes.index(entry_hash)
    except ValueError:
        return {"merkle_root": "", "proof_path": [], "leaf_index": -1, "verified": False}

    def _hash_func(data: bytes) -> str:
        try:
            import blake3 as _blake3  # type: ignore[import-untyped]
            return _blake3.blake3(data).hexdigest()
        except ImportError:
            return hashlib.sha256(data).hexdigest()

    if len(all_hashes) == 1:
        return {"merkle_root": _hash_func(entry_hash.encode()),
                "proof_path": [], "leaf_index": 0, "verified": True}

    current_level = [_hash_func(h.encode()) for h in all_hashes]
    proof_path: List[str] = []
    current_idx = idx

    while len(current_level) > 1:
        if len(current_level) % 2 != 0:
            current_level.append(current_level[-1])

        if current_idx % 2 == 0:
            if current_idx + 1 < len(current_level):
                proof_path.append(current_level[current_idx + 1])
        else:
            proof_path.append(current_level[current_idx - 1])

        next_level: List[str] = []
        for i in range(0, len(current_level), 2):
            combined = (current_level[i] + current_level[i + 1]).encode()
            next_level.append(_hash_func(combined))
        current_idx //= 2
        current_level = next_level

    root = _hash_func(current_level[0].encode()) if current_level else ""
    return {"merkle_root": root, "proof_path": proof_path,
            "leaf_index": idx, "verified": True}


def batch_verify_chains(
    chains: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    """Batch-verify multiple Merkle chains."""
    if HAS_NATIVE:
        return _rust_batch_verify_chains(chains)
    # Pure Python fallback
    return {chain_id: verify_merkle_chain(entries)
            for chain_id, entries in chains.items()}
