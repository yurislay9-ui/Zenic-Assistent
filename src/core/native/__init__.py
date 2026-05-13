"""
Zenic-Agents Native Extension Wrapper
======================================

Provides a unified interface to native Rust functions via PyO3,
with automatic fallback to pure Python implementations when the
Rust extension is not available.

Usage::

    from core.native import (
        HAS_NATIVE,
        # Crypto
        pbkdf2_derive_key,
        argon2id_hash,
        constant_time_compare,
        # Hash
        blake3_hash,
        xxhash64,
        merkle_root,
        # Forensic (A1)
        forensic_hash,
        chain_hash,
        verify_merkle_chain,
        merkle_proof,
        batch_verify_chains,
        # Rollback (A3)
        snapshot_file,
        restore_file,
        verify_rollback_readiness,
        file_hash,
        # EventBus (B1)
        wildcard_match,
        resolve_routes,
        batch_resolve_routes,
        deduplicate_events,
        sort_by_priority,
        # Simulation (C1)
        topological_sort,
        detect_cycles,
        aggregate_impact,
        simulate_dag,
        # Risk (F3)
        calculate_blast_radius,
        propagate_risks,
        find_critical_path,
        compute_reachability,
        multi_node_blast_radius,
    )
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import logging
import re
import shutil
import fnmatch
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("zenic_agents.core.native")

# ---------------------------------------------------------------------------
# Detect native extension
# ---------------------------------------------------------------------------

HAS_NATIVE: bool = False
_native_module: Optional[Any] = None

try:
    from _zenic_native import (  # type: ignore[import-not-found]
        # Crypto
        argon2id_hash as _rust_argon2id_hash,
        blake3_hash as _rust_blake3_hash,
        constant_time_compare as _rust_constant_time_compare,
        merkle_root as _rust_merkle_root,
        pbkdf2_derive_key as _rust_pbkdf2_derive_key,
        xxhash64 as _rust_xxhash64,
        # Forensic (A1)
        forensic_hash as _rust_forensic_hash,
        chain_hash as _rust_chain_hash,
        verify_merkle_chain as _rust_verify_merkle_chain,
        merkle_proof as _rust_merkle_proof,
        batch_verify_chains as _rust_batch_verify_chains,
        # Rollback (A3)
        snapshot_file as _rust_snapshot_file,
        restore_file as _rust_restore_file,
        verify_rollback_readiness as _rust_verify_rollback_readiness,
        file_hash as _rust_file_hash,
        # EventBus (B1)
        wildcard_match as _rust_wildcard_match,
        resolve_routes as _rust_resolve_routes,
        batch_resolve_routes as _rust_batch_resolve_routes,
        deduplicate_events as _rust_deduplicate_events,
        sort_by_priority as _rust_sort_by_priority,
        # Simulation (C1)
        topological_sort as _rust_topological_sort,
        detect_cycles as _rust_detect_cycles,
        aggregate_impact as _rust_aggregate_impact,
        simulate_dag as _rust_simulate_dag,
        # Risk (F3)
        calculate_blast_radius as _rust_calculate_blast_radius,
        propagate_risks as _rust_propagate_risks,
        find_critical_path as _rust_find_critical_path,
        compute_reachability as _rust_compute_reachability,
        multi_node_blast_radius as _rust_multi_node_blast_radius,
    )

    HAS_NATIVE = True
    _native_module = True
    logger.info("Native Rust extension (_zenic_native) loaded successfully")
except ImportError:
    HAS_NATIVE = False
    _native_module = None
    logger.info(
        "Native Rust extension not available — using pure Python fallbacks"
    )

# ---------------------------------------------------------------------------
# Import pure Python fallbacks for original functions
# ---------------------------------------------------------------------------

from ._fallbacks import (
    argon2id_hash as _py_argon2id_hash,
    blake3_hash as _py_blake3_hash,
    constant_time_compare as _py_constant_time_compare,
    merkle_root as _py_merkle_root,
    pbkdf2_derive_key as _py_pbkdf2_derive_key,
    xxhash64 as _py_xxhash64,
)

# ---------------------------------------------------------------------------
# Original Crypto/Hash API — delegates to native or pure Python
# ---------------------------------------------------------------------------


def pbkdf2_derive_key(
    password: bytes, salt: bytes, iterations: int, key_length: int
) -> bytes:
    if HAS_NATIVE:
        return _rust_pbkdf2_derive_key(password, salt, iterations, key_length)
    return _py_pbkdf2_derive_key(password, salt, iterations, key_length)


def argon2id_hash(
    password: bytes,
    salt: bytes,
    memory_cost: int,
    time_cost: int,
    parallelism: int,
) -> bytes:
    if HAS_NATIVE:
        return _rust_argon2id_hash(
            password, salt, memory_cost, time_cost, parallelism
        )
    return _py_argon2id_hash(
        password, salt, memory_cost, time_cost, parallelism
    )


def constant_time_compare(a: bytes, b: bytes) -> bool:
    if HAS_NATIVE:
        return _rust_constant_time_compare(a, b)
    return _py_constant_time_compare(a, b)


def blake3_hash(data: bytes) -> str:
    if HAS_NATIVE:
        return _rust_blake3_hash(data)
    return _py_blake3_hash(data)


def xxhash64(data: bytes, seed: int = 0) -> int:
    if HAS_NATIVE:
        return _rust_xxhash64(data, seed)
    return _py_xxhash64(data, seed)


def merkle_root(leaves: List[bytes]) -> str:
    if HAS_NATIVE:
        return _rust_merkle_root(leaves)
    return _py_merkle_root(leaves)


# ===========================================================================
# FORENSIC AUDIT (A1) — Merkle chain verification, integrity
# ===========================================================================


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
                # Check if parent exists in any group
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


# ===========================================================================
# COORDINATED ROLLBACK (A3) — Atomic cross-resource
# ===========================================================================


def snapshot_file(source_path: str, backup_path: str) -> Dict[str, Any]:
    """Create a backup snapshot of a file with BLAKE3 checksum."""
    if HAS_NATIVE:
        return _rust_snapshot_file(source_path, backup_path)
    # Pure Python fallback
    src = Path(source_path)
    if not src.exists():
        return {"success": False, "source_path": source_path,
                "backup_path": backup_path,
                "error": f"Source file does not exist: {source_path}"}
    try:
        data = src.read_bytes()
        checksum = hashlib.sha256(data).hexdigest()
        bk = Path(backup_path)
        bk.parent.mkdir(parents=True, exist_ok=True)
        bk.write_bytes(data)
        return {"success": True, "source_path": source_path,
                "backup_path": backup_path, "checksum": checksum,
                "file_size": len(data)}
    except Exception as exc:
        return {"success": False, "source_path": source_path,
                "backup_path": backup_path, "error": str(exc)}


def restore_file(
    backup_path: str, target_path: str, expected_checksum: str,
) -> Dict[str, Any]:
    """Restore a file from a backup with checksum verification."""
    if HAS_NATIVE:
        return _rust_restore_file(backup_path, target_path, expected_checksum)
    # Pure Python fallback
    bk = Path(backup_path)
    if not bk.exists():
        return {"success": False, "backup_path": backup_path,
                "target_path": target_path, "checksum_verified": False,
                "error": f"Backup file does not exist: {backup_path}"}
    try:
        data = bk.read_bytes()
        actual_checksum = hashlib.sha256(data).hexdigest()
        if actual_checksum != expected_checksum:
            return {"success": False, "backup_path": backup_path,
                    "target_path": target_path, "checksum_verified": False,
                    "error": f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}"}
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return {"success": True, "backup_path": backup_path,
                "target_path": target_path, "checksum_verified": True,
                "bytes_restored": len(data)}
    except Exception as exc:
        return {"success": False, "backup_path": backup_path,
                "target_path": target_path, "checksum_verified": False,
                "error": str(exc)}


def verify_rollback_readiness(
    resources: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Verify that all resources needed for rollback are available."""
    if HAS_NATIVE:
        return _rust_verify_rollback_readiness(resources)
    # Pure Python fallback
    total = len(resources)
    verified = 0
    failed: List[Dict[str, Any]] = []

    for res in resources:
        rtype = res.get("resource_type", "")
        if rtype == "file":
            bp = res.get("backup_path", "")
            ec = res.get("expected_checksum", "")
            bk = Path(bp) if bp else None
            if bk is None or not bk.exists():
                failed.append({"resource_type": rtype, "backup_path": bp,
                               "reason": "Backup file does not exist"})
                continue
            try:
                data = bk.read_bytes()
                actual = hashlib.sha256(data).hexdigest()
                if ec and actual != ec:
                    failed.append({"resource_type": rtype, "backup_path": bp,
                                   "reason": f"Checksum mismatch: expected {ec}, got {actual}"})
                else:
                    verified += 1
            except Exception as exc:
                failed.append({"resource_type": rtype, "backup_path": bp,
                               "reason": str(exc)})
        else:
            verified += 1

    return {"all_verified": len(failed) == 0, "total_resources": total,
            "verified_count": verified, "failed": failed}


def file_hash(file_path: str) -> str:
    """Compute the BLAKE3/SHA-256 hash of a file."""
    if HAS_NATIVE:
        return _rust_file_hash(file_path)
    # Pure Python fallback
    data = Path(file_path).read_bytes()
    if not data:
        raise RuntimeError(f"File is empty: {file_path}")
    try:
        import blake3 as _blake3  # type: ignore[import-untyped]
        return _blake3.blake3(data).hexdigest()
    except ImportError:
        return hashlib.sha256(data).hexdigest()


# ===========================================================================
# HIGH-SPEED EVENT BUS (B1) — Low-latency dispatch
# ===========================================================================


def wildcard_match(pattern: str, text: str) -> bool:
    """Fast wildcard pattern matching supporting * and ? wildcards."""
    if HAS_NATIVE:
        return _rust_wildcard_match(pattern, text)
    # Pure Python fallback using fnmatch
    return fnmatch.fnmatch(text, pattern)


def resolve_routes(
    event_topic: str, subscriptions: List[Dict[str, Any]],
) -> List[str]:
    """Resolve which handlers should receive an event."""
    if HAS_NATIVE:
        return _rust_resolve_routes(event_topic, subscriptions)
    # Pure Python fallback
    _priority_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
    matched: List[Tuple[int, str]] = []
    for sub in subscriptions:
        if not sub.get("active", True):
            continue
        pattern = sub.get("pattern", "")
        handler_id = sub.get("handler_id", "")
        priority = sub.get("priority", "normal").lower()
        if fnmatch.fnmatch(event_topic, pattern):
            matched.append((_priority_order.get(priority, 2), handler_id))
    matched.sort(key=lambda x: x[0])
    return [hid for _, hid in matched]


def batch_resolve_routes(
    event_topics: List[str],
    subscriptions: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """Batch resolve routes for multiple events."""
    if HAS_NATIVE:
        return _rust_batch_resolve_routes(event_topics, subscriptions)
    # Pure Python fallback
    return {topic: resolve_routes(topic, subscriptions) for topic in event_topics}


def deduplicate_events(
    new_fingerprints: List[str],
    seen_fingerprints: Set[str],
) -> Dict[str, Any]:
    """Deduplicate events by fingerprint."""
    if HAS_NATIVE:
        return _rust_deduplicate_events(new_fingerprints, seen_fingerprints)
    # Pure Python fallback
    unique: List[str] = []
    duplicates: List[str] = []
    for fp in new_fingerprints:
        if fp in seen_fingerprints:
            duplicates.append(fp)
        else:
            unique.append(fp)
    return {"unique": unique, "duplicates": duplicates}


def sort_by_priority(
    events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Sort events by priority (critical first)."""
    if HAS_NATIVE:
        return _rust_sort_by_priority(events)
    # Pure Python fallback
    _priority_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
    return sorted(events, key=lambda e: _priority_order.get(
        e.get("priority", "normal").lower(), 2))


# ===========================================================================
# DRY-RUN SIMULATION (C1) — DAG extension
# ===========================================================================


def topological_sort(
    nodes: List[str], edges: List[Tuple[str, str]],
) -> Dict[str, Any]:
    """Topological sort of a DAG using Kahn's algorithm."""
    if HAS_NATIVE:
        return _rust_topological_sort(nodes, edges)
    # Pure Python fallback
    adj: Dict[str, List[str]] = defaultdict(list)
    in_degree: Dict[str, int] = defaultdict(int)

    for node in nodes:
        in_degree[node] = 0
    for src, dst in edges:
        adj[src].append(dst)
        in_degree[dst] += 1

    queue = deque(n for n, d in in_degree.items() if d == 0)
    sorted_nodes: List[str] = []

    while queue:
        node = queue.popleft()
        sorted_nodes.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    has_cycle = len(sorted_nodes) != len(nodes)
    cycle_nodes = [n for n in nodes if n not in set(sorted_nodes)] if has_cycle else []

    return {"sorted": sorted_nodes, "has_cycle": has_cycle,
            "cycle_nodes": cycle_nodes}


def detect_cycles(
    nodes: List[str], edges: List[Tuple[str, str]],
) -> Dict[str, Any]:
    """Detect cycles in a directed graph using DFS."""
    if HAS_NATIVE:
        return _rust_detect_cycles(nodes, edges)
    # Pure Python fallback — reuse topological sort
    result = topological_sort(nodes, edges)
    return {"has_cycle": result["has_cycle"],
            "cycle_path": result.get("cycle_nodes", [])}


def aggregate_impact(
    sorted_nodes: List[str],
    edges: List[Tuple[str, str]],
    risk_scores: Dict[str, float],
    strategy: str,
) -> Dict[str, Any]:
    """Aggregate risk scores across a DAG execution path."""
    if HAS_NATIVE:
        return _rust_aggregate_impact(sorted_nodes, edges, risk_scores, strategy)
    # Pure Python fallback
    if not sorted_nodes:
        return {"aggregated_score": 0.0, "strategy": strategy,
                "node_count": 0, "max_score": 0.0, "min_score": 0.0,
                "high_risk_nodes": []}

    scores = [risk_scores.get(n, 0.0) for n in sorted_nodes]
    high_risk = [n for n in sorted_nodes if risk_scores.get(n, 0.0) >= 0.7]

    if strategy == "max":
        aggregated = max(scores) if scores else 0.0
    elif strategy == "sum":
        aggregated = sum(scores)
    elif strategy == "avg":
        aggregated = sum(scores) / len(scores) if scores else 0.0
    elif strategy == "weighted_avg":
        total_weight = sum(range(1, len(scores) + 1))
        aggregated = sum(s * (i + 1) for i, s in enumerate(scores)) / total_weight
    else:
        raise ValueError(f"Unknown strategy '{strategy}'. Use: max, sum, avg, weighted_avg")

    return {"aggregated_score": aggregated, "strategy": strategy,
            "node_count": len(sorted_nodes),
            "max_score": max(scores) if scores else 0.0,
            "min_score": min(scores) if scores else 0.0,
            "high_risk_nodes": high_risk}


def simulate_dag(
    nodes: List[Dict[str, Any]],
    edges: List[Tuple[str, str]],
) -> Dict[str, Any]:
    """Simulate a DAG execution without side effects."""
    if HAS_NATIVE:
        return _rust_simulate_dag(nodes, edges)
    # Pure Python fallback
    node_ids = [n.get("id", "") for n in nodes]
    node_risks = {n.get("id", ""): n.get("risk_score", 0.0) for n in nodes}
    node_durations = {n.get("id", ""): n.get("estimated_duration_ms", 0) for n in nodes}

    sort_result = topological_sort(node_ids, edges)
    sorted_ids = sort_result["sorted"]
    has_cycle = sort_result["has_cycle"]

    total_duration = sum(node_durations.get(n, 0) for n in sorted_ids)
    risks = [node_risks.get(n, 0.0) for n in sorted_ids]
    aggregated_risk = max(risks) if risks else 0.0
    high_risk_path = [n for n in sorted_ids if node_risks.get(n, 0.0) >= 0.7]

    return {"total_nodes": len(node_ids), "execution_order": sorted_ids,
            "total_estimated_duration_ms": total_duration,
            "aggregated_risk": aggregated_risk,
            "high_risk_path": high_risk_path, "has_cycle": has_cycle}


# ===========================================================================
# RISK PREDICTION (F3) — Blast radius, propagation
# ===========================================================================


def calculate_blast_radius(
    node_id: str, edges: List[Tuple[str, str]],
) -> Dict[str, Any]:
    """Calculate the blast radius of a node failure."""
    if HAS_NATIVE:
        return _rust_calculate_blast_radius(node_id, edges)
    # Pure Python fallback
    forward: Dict[str, List[str]] = defaultdict(list)
    for src, dst in edges:
        forward[src].append(dst)

    direct = set(forward.get(node_id, []))
    visited: Set[str] = set()
    queue = deque([node_id])

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in forward.get(current, []):
            if neighbor not in visited:
                queue.append(neighbor)

    visited.discard(node_id)
    transitive = visited - direct
    blast_size = len(visited)
    risk_level = "low" if blast_size == 0 else "medium" if blast_size <= 3 else "high" if blast_size <= 10 else "critical"

    return {"source_node": node_id, "blast_radius": list(visited),
            "direct_dependents": list(direct),
            "transitive_dependents": list(transitive),
            "blast_radius_size": blast_size, "risk_level": risk_level}


def propagate_risks(
    nodes: List[str],
    edges: List[Tuple[str, str]],
    base_risks: Dict[str, float],
    decay: float,
) -> Dict[str, Any]:
    """Propagate risk scores through the DAG."""
    if HAS_NATIVE:
        return _rust_propagate_risks(nodes, edges, base_risks, decay)
    # Pure Python fallback
    if not (0.0 <= decay <= 1.0):
        raise ValueError("decay must be between 0.0 and 1.0")

    reverse_adj: Dict[str, List[str]] = defaultdict(list)
    for src, dst in edges:
        reverse_adj[dst].append(src)

    effective: Dict[str, float] = {}
    risk_paths: Dict[str, List[str]] = {}

    for node in nodes:
        own_risk = base_risks.get(node, 0.0)
        incoming = reverse_adj.get(node, [])
        max_propagated = 0.0
        max_source = ""
        for src in incoming:
            src_eff = effective.get(src, 0.0)
            propagated = src_eff * decay
            if propagated > max_propagated:
                max_propagated = propagated
                max_source = src

        effective_risk = max(own_risk, max_propagated)
        effective[node] = effective_risk

        if max_source and max_propagated > own_risk:
            path = risk_paths.get(max_source, [])[:]
            path.append(node)
            risk_paths[node] = path
        else:
            risk_paths[node] = [node]

    max_effective = max(effective.values()) if effective else 0.0
    high_risk = [n for n, r in effective.items() if r >= 0.7]

    return {"effective_risks": effective, "max_effective_risk": max_effective,
            "high_risk_nodes": high_risk, "risk_paths": risk_paths}


def find_critical_path(
    nodes: List[str],
    edges: List[Tuple[str, str]],
    durations: Dict[str, int],
) -> Dict[str, Any]:
    """Identify the critical path in the DAG."""
    if HAS_NATIVE:
        return _rust_find_critical_path(nodes, edges, durations)
    # Pure Python fallback
    predecessors: Dict[str, List[str]] = defaultdict(list)
    for node in nodes:
        predecessors[node] = []
    for src, dst in edges:
        predecessors[dst].append(src)

    earliest_finish: Dict[str, int] = {}
    pred_on_path: Dict[str, Optional[str]] = {}

    for node in nodes:
        node_dur = durations.get(node, 0)
        max_pred = 0
        best_pred = None
        for pred in predecessors[node]:
            pf = earliest_finish.get(pred, 0)
            if pf > max_pred:
                max_pred = pf
                best_pred = pred
        earliest_finish[node] = max_pred + node_dur
        pred_on_path[node] = best_pred

    end_node = max(earliest_finish, key=earliest_finish.get) if earliest_finish else ""
    total_duration = earliest_finish.get(end_node, 0)

    critical_path: List[str] = []
    current: Optional[str] = end_node
    while current:
        critical_path.append(current)
        current = pred_on_path.get(current)
    critical_path.reverse()

    critical_set = set(critical_path)
    is_on_critical = {n: n in critical_set for n in nodes}

    return {"critical_path": critical_path,
            "total_duration_ms": total_duration,
            "is_on_critical_path": is_on_critical}


def compute_reachability(
    source_nodes: List[str], edges: List[Tuple[str, str]],
) -> Dict[str, Any]:
    """Compute reachability from source nodes."""
    if HAS_NATIVE:
        return _rust_compute_reachability(source_nodes, edges)
    # Pure Python fallback
    forward: Dict[str, List[str]] = defaultdict(list)
    for src, dst in edges:
        forward[src].append(dst)

    all_reachable: Set[str] = set()
    by_source: Dict[str, List[str]] = {}

    for source in source_nodes:
        visited: Set[str] = set()
        queue = deque([source])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for neighbor in forward.get(current, []):
                if neighbor not in visited:
                    queue.append(neighbor)
        visited.discard(source)
        all_reachable.update(visited)
        by_source[source] = list(visited)

    return {"reachable": list(all_reachable),
            "reachable_count": sum(len(v) for v in by_source.values()),
            "by_source": by_source}


def multi_node_blast_radius(
    failed_nodes: List[str], edges: List[Tuple[str, str]],
) -> Dict[str, Any]:
    """Calculate combined blast radius for multiple node failures."""
    if HAS_NATIVE:
        return _rust_multi_node_blast_radius(failed_nodes, edges)
    # Pure Python fallback
    forward: Dict[str, List[str]] = defaultdict(list)
    for src, dst in edges:
        forward[src].append(dst)

    failed_set = set(failed_nodes)
    visited: Set[str] = set()
    queue = deque(failed_nodes)

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in forward.get(current, []):
            if neighbor not in visited:
                queue.append(neighbor)

    blast_radius = [n for n in visited if n not in failed_set]
    blast_size = len(blast_radius)
    risk_level = "low" if blast_size == 0 else "medium" if blast_size <= 5 else "high" if blast_size <= 15 else "critical"

    per_node: Dict[str, Dict[str, Any]] = {}
    for node in failed_nodes:
        node_result = calculate_blast_radius(node, edges)
        per_node[node] = node_result

    return {"combined_blast_radius": blast_radius,
            "blast_radius_size": blast_size,
            "risk_level": risk_level,
            "per_node": per_node}


# ---------------------------------------------------------------------------
# Convenience re-exports
# ---------------------------------------------------------------------------

__all__ = [
    # Feature flag
    "HAS_NATIVE",
    # Crypto
    "argon2id_hash",
    "constant_time_compare",
    "pbkdf2_derive_key",
    # Hash
    "blake3_hash",
    "merkle_root",
    "xxhash64",
    # Forensic (A1)
    "batch_verify_chains",
    "chain_hash",
    "forensic_hash",
    "merkle_proof",
    "verify_merkle_chain",
    # Rollback (A3)
    "file_hash",
    "restore_file",
    "snapshot_file",
    "verify_rollback_readiness",
    # EventBus (B1)
    "batch_resolve_routes",
    "deduplicate_events",
    "resolve_routes",
    "sort_by_priority",
    "wildcard_match",
    # Simulation (C1)
    "aggregate_impact",
    "detect_cycles",
    "simulate_dag",
    "topological_sort",
    # Risk (F3)
    "calculate_blast_radius",
    "compute_reachability",
    "find_critical_path",
    "multi_node_blast_radius",
    "propagate_risks",
]
