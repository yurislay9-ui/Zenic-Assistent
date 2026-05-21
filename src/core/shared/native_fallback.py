"""
ZENIC-AGENTS — Native Fallback Registry (H-82: Complete Fallback Coverage).

When _zenic_native (Rust PyO3 module) is unavailable, this registry
provides Python fallbacks for ALL critical functions. This prevents silent
capability loss when the Rust extension fails to load.

The fallback implementations are imported from the existing pure-Python
implementations in src.core.native._fallbacks and src.core.native._forensic.

Usage:
    from src.core.shared.native_fallback import call_native

    result = call_native("blake3_hash", data)
    # Tries _zenic_native.blake3_hash first, falls back to Python implementation
"""

import hashlib
import hmac as _hmac
import logging
import os
import re
import shutil
from collections import defaultdict
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

__all__ = ["call_native", "register_fallback"]

# Registry of Python fallback implementations
_FALLBACKS: Dict[str, Callable] = {}


def register_fallback(name: str, fn: Callable) -> None:
    """Register a Python fallback for a Rust native function.

    Args:
        name: The function name as exposed by _zenic_native.
        fn: The Python fallback implementation.
    """
    _FALLBACKS[name] = fn
    logger.debug("Registered Python fallback for _zenic_native.%s", name)


def call_native(name: str, *args: Any, **kwargs: Any) -> Any:
    """Call a Rust native function with Python fallback.

    Tries _zenic_native.<name> first. If the module is unavailable
    or the function doesn't exist, falls back to a registered Python
    implementation.

    Args:
        name: The function name in _zenic_native.
        *args: Positional arguments for the function.
        **kwargs: Keyword arguments for the function.

    Returns:
        The function result.

    Raises:
        RuntimeError: If native call fails and no fallback is registered.
    """
    try:
        import _zenic_native
        fn = getattr(_zenic_native, name)
        return fn(*args, **kwargs)
    except ImportError:
        logger.debug("_zenic_native not available, checking fallbacks")
    except AttributeError:
        logger.warning("_zenic_native.%s not found, checking fallbacks", name)
    except Exception as exc:
        logger.warning("_zenic_native.%s failed: %s, checking fallbacks", name, exc)

    # Try Python fallback
    if name in _FALLBACKS:
        logger.info("Using Python fallback for _zenic_native.%s", name)
        return _FALLBACKS[name](*args, **kwargs)

    raise RuntimeError(
        f"_zenic_native.{name} is unavailable and no Python fallback is registered. "
        f"Install the Rust extension or register a fallback with register_fallback()."
    )


# ════════════════════════════════════════════════════════════════
#  BUILT-IN PYTHON FALLBACKS — Crypto (core)
# ════════════════════════════════════════════════════════════════

def _sha256_hash(data: str) -> str:
    """Python fallback for blake3_hash (uses SHA-256 instead)."""
    return hashlib.sha256(data.encode()).hexdigest()


def _hmac_sign(data: str, secret_key: str) -> str:
    """Python fallback for sign_data."""
    return _hmac.new(secret_key.encode(), data.encode(), hashlib.sha256).hexdigest()


def _hmac_verify(data: str, signature: str, secret_key: str) -> bool:
    """Python fallback for verify_signature."""
    expected = _hmac.new(secret_key.encode(), data.encode(), hashlib.sha256).hexdigest()
    return _hmac.compare_digest(expected, signature)


def _pbkdf2_derive_key(password: bytes, salt: bytes, iterations: int, key_length: int) -> bytes:
    """Python fallback for pbkdf2_derive_key."""
    if not password:
        raise ValueError("password must not be empty")
    if not salt:
        raise ValueError("salt must not be empty")
    return hashlib.pbkdf2_hmac("sha256", password, salt, iterations, key_length)


def _argon2id_hash(password: bytes, salt: bytes, memory_cost: int, time_cost: int, parallelism: int) -> bytes:
    """Python fallback for argon2id_hash — tries argon2-cffi, then PBKDF2."""
    try:
        from argon2 import low_level  # type: ignore[import-untyped]
        return low_level.hash_secret_raw(
            secret=password, salt=salt, time_cost=time_cost,
            memory_cost=memory_cost, parallelism=parallelism,
            hash_len=32, type=low_level.Type.ID,
        )
    except ImportError:
        logger.warning("argon2 not available, falling back to PBKDF2 for argon2id_hash")
        return hashlib.pbkdf2_hmac("sha256", password, salt, time_cost * 100000, 32)


def _constant_time_compare(a: bytes, b: bytes) -> bool:
    """Python fallback for constant_time_compare."""
    return _hmac.compare_digest(a, b)


# ════════════════════════════════════════════════════════════════
#  BUILT-IN PYTHON FALLBACKS — Hash
# ════════════════════════════════════════════════════════════════

def _blake3_hash_fallback(data: bytes) -> str:
    """Python fallback for blake3_hash — tries blake3 package, then SHA-256."""
    try:
        import blake3 as _blake3  # type: ignore[import-untyped]
        return _blake3.blake3(data).hexdigest()
    except ImportError:
        return hashlib.sha256(data).hexdigest()


def _xxhash64_fallback(data: bytes, seed: int) -> int:
    """Python fallback for xxhash64 — tries xxhash package, then FNV-1a."""
    try:
        import xxhash  # type: ignore[import-untyped]
        return xxhash.xxh64(data, seed=seed).intdigest()
    except ImportError:
        FNV_OFFSET = 14695981039346656037
        FNV_PRIME = 1099511628211
        MASK = (1 << 64) - 1
        h = (FNV_OFFSET ^ seed) & MASK
        for byte in data:
            h ^= byte
            h = (h * FNV_PRIME) & MASK
        return h


def _merkle_root_fallback(leaves: List[bytes]) -> str:
    """Python fallback for merkle_root using BLAKE3 or SHA-256."""
    if not leaves:
        raise ValueError("leaves must not be empty")

    def _hash_func(data: bytes) -> bytes:
        try:
            import blake3 as _blake3  # type: ignore[import-untyped]
            return _blake3.blake3(data).digest()
        except ImportError:
            return hashlib.sha256(data).digest()

    if len(leaves) == 1:
        return _hash_func(leaves[0]).hex()

    current_level: List[bytes] = [_hash_func(leaf) for leaf in leaves]
    while len(current_level) > 1:
        if len(current_level) % 2 != 0:
            current_level.append(current_level[-1])
        next_level: List[bytes] = []
        for i in range(0, len(current_level), 2):
            combined = current_level[i] + current_level[i + 1]
            next_level.append(_hash_func(combined))
        current_level = next_level
    return current_level[0].hex()


# ════════════════════════════════════════════════════════════════
#  BUILT-IN PYTHON FALLBACKS — Forensic Audit (A1)
# ════════════════════════════════════════════════════════════════

def _forensic_hash(
    entry_id: str, tenant_id: str, event_type: str,
    description: str, actor: str, timestamp: str, metadata_json: str,
) -> str:
    """Python fallback for forensic_hash."""
    payload = "|".join([entry_id, tenant_id, event_type, description, actor, timestamp, metadata_json])
    try:
        import blake3 as _blake3  # type: ignore[import-untyped]
        return _blake3.blake3(payload.encode()).hexdigest()
    except ImportError:
        return hashlib.sha256(payload.encode()).hexdigest()


def _chain_hash(parent_hash: str, entry_hash: str) -> str:
    """Python fallback for chain_hash."""
    combined = (parent_hash + entry_hash).encode()
    try:
        import blake3 as _blake3  # type: ignore[import-untyped]
        return _blake3.blake3(combined).hexdigest()
    except ImportError:
        return hashlib.sha256(combined).hexdigest()


def _verify_merkle_chain(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Python fallback for verify_merkle_chain."""
    if not entries:
        return {"is_valid": True, "total_entries": 0, "valid_entries": 0,
                "broken_links": [], "root_hash": ""}

    total = len(entries)
    valid_count = 0
    broken_links: List[Dict[str, Any]] = []

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
                parent_exists = any(e.get("hash_sha256") == parent_hash for e in entries)
                if parent_exists:
                    valid_count += 1
                else:
                    broken_links.append({
                        "file_path": fp, "entry_id": row.get("id"),
                        "expected_parent_hash": parent_hash,
                        "actual_parent_hash": parent_hash,
                        "entry_hash": row.get("hash_sha256", ""),
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
                })

    root_hash = entries[-1].get("hash_sha256", "") if entries else ""
    return {"is_valid": len(broken_links) == 0, "total_entries": total,
            "valid_entries": valid_count, "broken_links": broken_links,
            "root_hash": root_hash}


def _merkle_proof(entry_hash: str, all_hashes: List[str]) -> Dict[str, Any]:
    """Python fallback for merkle_proof."""
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
        next_level = []
        for i in range(0, len(current_level), 2):
            combined = (current_level[i] + current_level[i + 1]).encode()
            next_level.append(_hash_func(combined))
        current_idx //= 2
        current_level = next_level

    root = _hash_func(current_level[0].encode()) if current_level else ""
    return {"merkle_root": root, "proof_path": proof_path,
            "leaf_index": idx, "verified": True}


def _batch_verify_chains(chains: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    """Python fallback for batch_verify_chains."""
    return {chain_id: _verify_merkle_chain(entries) for chain_id, entries in chains.items()}


# ════════════════════════════════════════════════════════════════
#  BUILT-IN PYTHON FALLBACKS — Rollback (A3)
# ════════════════════════════════════════════════════════════════

def _snapshot_file(file_path: str, snapshot_dir: str) -> str:
    """Python fallback for snapshot_file — copies file to snapshot directory."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    os.makedirs(snapshot_dir, exist_ok=True)
    basename = os.path.basename(file_path)
    dest = os.path.join(snapshot_dir, f"{basename}.snap")
    shutil.copy2(file_path, dest)
    return dest


def _restore_file(snapshot_path: str, target_path: str) -> str:
    """Python fallback for restore_file — restores file from snapshot."""
    if not os.path.isfile(snapshot_path):
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")
    shutil.copy2(snapshot_path, target_path)
    return target_path


def _verify_rollback_readiness(snapshot_dir: str) -> Dict[str, Any]:
    """Python fallback for verify_rollback_readiness — checks snapshot directory."""
    if not os.path.isdir(snapshot_dir):
        return {"ready": False, "snapshots": 0, "reason": "Snapshot directory does not exist"}
    snaps = [f for f in os.listdir(snapshot_dir) if f.endswith(".snap")]
    return {"ready": len(snaps) > 0, "snapshots": len(snaps), "files": snaps}


def _file_hash(file_path: str) -> str:
    """Python fallback for file_hash — computes SHA-256 of file contents."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ════════════════════════════════════════════════════════════════
#  BUILT-IN PYTHON FALLBACKS — EventBus (B1)
# ════════════════════════════════════════════════════════════════

def _wildcard_match(pattern: str, topic: str) -> bool:
    """Python fallback for wildcard_match — matches event bus topic patterns."""
    regex = pattern.replace(".", r"\.").replace("*", "[^.]+").replace("#", ".*")
    return bool(re.fullmatch(regex, topic))


def _resolve_routes(pattern: str, registered_topics: List[str]) -> List[str]:
    """Python fallback for resolve_routes — resolves pattern to matching topics."""
    return [t for t in registered_topics if _wildcard_match(pattern, t)]


def _batch_resolve_routes(patterns: List[str], registered_topics: List[str]) -> Dict[str, List[str]]:
    """Python fallback for batch_resolve_routes."""
    return {p: _resolve_routes(p, registered_topics) for p in patterns}


def _deduplicate_events(events: List[Dict[str, Any]], key_field: str = "id") -> List[Dict[str, Any]]:
    """Python fallback for deduplicate_events."""
    seen = set()
    result = []
    for ev in events:
        key = ev.get(key_field, id(ev))
        if key not in seen:
            seen.add(key)
            result.append(ev)
    return result


def _sort_by_priority(events: List[Dict[str, Any]], priority_field: str = "priority") -> List[Dict[str, Any]]:
    """Python fallback for sort_by_priority."""
    return sorted(events, key=lambda e: e.get(priority_field, 0), reverse=True)


# ════════════════════════════════════════════════════════════════
#  BUILT-IN PYTHON FALLBACKS — Simulation (C1)
# ════════════════════════════════════════════════════════════════

def _topological_sort(nodes: List[str], edges: List[tuple]) -> List[str]:
    """Python fallback for topological_sort — Kahn's algorithm."""
    in_degree = {n: 0 for n in nodes}
    graph: Dict[str, List[str]] = {n: [] for n in nodes}
    for src, dst in edges:
        graph[src].append(dst)
        in_degree[dst] = in_degree.get(dst, 0) + 1

    queue = [n for n in nodes if in_degree[n] == 0]
    result = []
    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    return result


def _detect_cycles(nodes: List[str], edges: List[tuple]) -> List[List[str]]:
    """Python fallback for detect_cycles — DFS cycle detection."""
    graph: Dict[str, List[str]] = {n: [] for n in nodes}
    for src, dst in edges:
        graph[src].append(dst)

    cycles = []
    visited = set()
    path = []
    path_set = set()

    def dfs(node: str) -> None:
        visited.add(node)
        path.append(node)
        path_set.add(node)
        for neighbor in graph.get(node, []):
            if neighbor in path_set:
                cycle_start = path.index(neighbor)
                cycles.append(path[cycle_start:] + [neighbor])
            elif neighbor not in visited:
                dfs(neighbor)
        path.pop()
        path_set.discard(node)

    for node in nodes:
        if node not in visited:
            dfs(node)
    return cycles


def _aggregate_impact(changes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Python fallback for aggregate_impact — sums risk scores."""
    total_risk = sum(c.get("risk_score", 0) for c in changes)
    affected_nodes = set()
    for c in changes:
        if "node" in c:
            affected_nodes.add(c["node"])
        if "affected_nodes" in c:
            affected_nodes.update(c["affected_nodes"])
    return {"total_risk": total_risk, "affected_count": len(affected_nodes),
            "affected_nodes": list(affected_nodes)}


def _simulate_dag(nodes: List[str], edges: List[tuple], change_node: str) -> Dict[str, Any]:
    """Python fallback for simulate_dag — BFS reachability from change_node."""
    graph: Dict[str, List[str]] = {n: [] for n in nodes}
    for src, dst in edges:
        graph[src].append(dst)

    visited = set()
    queue = [change_node]
    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                queue.append(neighbor)

    return {"change_node": change_node, "reachable": list(visited),
            "impact_radius": len(visited)}


# ════════════════════════════════════════════════════════════════
#  BUILT-IN PYTHON FALLBACKS — Risk (F3)
# ════════════════════════════════════════════════════════════════

def _calculate_blast_radius(node: str, edges: List[tuple], max_depth: int = 10) -> Dict[str, Any]:
    """Python fallback for calculate_blast_radius — BFS with depth limit."""
    graph: Dict[str, List[str]] = {}
    for src, dst in edges:
        graph.setdefault(src, []).append(dst)

    visited = set()
    queue = [(node, 0)]
    while queue:
        current, depth = queue.pop(0)
        if current in visited or depth > max_depth:
            continue
        visited.add(current)
        for neighbor in graph.get(current, []):
            if neighbor not in visited:
                queue.append((neighbor, depth + 1))

    return {"center": node, "radius": len(visited), "affected": list(visited)}


def _propagate_risks(start_nodes: List[str], edges: List[tuple], initial_scores: Dict[str, float]) -> Dict[str, float]:
    """Python fallback for propagate_risks — simple risk propagation."""
    graph: Dict[str, List[str]] = {}
    for src, dst in edges:
        graph.setdefault(src, []).append(dst)

    scores = dict(initial_scores)
    for node in start_nodes:
        if node not in scores:
            scores[node] = 1.0

    # Simple propagation: each neighbor gets 50% of source risk
    for node in start_nodes:
        base_risk = scores.get(node, 1.0)
        for neighbor in graph.get(node, []):
            propagated = base_risk * 0.5
            scores[neighbor] = max(scores.get(neighbor, 0), propagated)

    return scores


def _find_critical_path(nodes: List[str], edges: List[tuple], scores: Dict[str, float]) -> List[str]:
    """Python fallback for find_critical_path — highest-risk path via greedy."""
    graph: Dict[str, List[str]] = {}
    for src, dst in edges:
        graph.setdefault(src, []).append(dst)

    # Start from highest-scored node
    start = max(scores, key=scores.get) if scores else (nodes[0] if nodes else "")
    path = [start]
    visited = {start}

    while True:
        current = path[-1]
        neighbors = [n for n in graph.get(current, []) if n not in visited]
        if not neighbors:
            break
        next_node = max(neighbors, key=lambda n: scores.get(n, 0))
        path.append(next_node)
        visited.add(next_node)

    return path


def _compute_reachability(nodes: List[str], edges: List[tuple]) -> Dict[str, List[str]]:
    """Python fallback for compute_reachability — all-pairs reachability."""
    graph: Dict[str, List[str]] = {n: [] for n in nodes}
    for src, dst in edges:
        graph.setdefault(src, []).append(dst)

    reachability: Dict[str, List[str]] = {}
    for node in nodes:
        visited = set()
        queue = [node]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for neighbor in graph.get(current, []):
                if neighbor not in visited:
                    queue.append(neighbor)
        reachability[node] = [n for n in visited if n != node]

    return reachability


def _multi_node_blast_radius(nodes: List[str], edges: List[tuple], max_depth: int = 10) -> Dict[str, Dict[str, Any]]:
    """Python fallback for multi_node_blast_radius."""
    return {node: _calculate_blast_radius(node, edges, max_depth) for node in nodes}


# ════════════════════════════════════════════════════════════════
#  REGISTER ALL FALLBACKS
# ════════════════════════════════════════════════════════════════

# Crypto (core)
register_fallback("blake3_hash", _blake3_hash_fallback)
register_fallback("sign_data", _hmac_sign)
register_fallback("verify_signature", _hmac_verify)
register_fallback("pbkdf2_derive_key", _pbkdf2_derive_key)
register_fallback("argon2id_hash", _argon2id_hash)
register_fallback("constant_time_compare", _constant_time_compare)

# Hash
register_fallback("xxhash64", _xxhash64_fallback)
register_fallback("merkle_root", _merkle_root_fallback)

# Forensic Audit (A1) — H-82: was missing
register_fallback("forensic_hash", _forensic_hash)
register_fallback("chain_hash", _chain_hash)
register_fallback("verify_merkle_chain", _verify_merkle_chain)
register_fallback("merkle_proof", _merkle_proof)
register_fallback("batch_verify_chains", _batch_verify_chains)

# Rollback (A3) — H-82: was missing
register_fallback("snapshot_file", _snapshot_file)
register_fallback("restore_file", _restore_file)
register_fallback("verify_rollback_readiness", _verify_rollback_readiness)
register_fallback("file_hash", _file_hash)

# EventBus (B1) — H-82: was missing
register_fallback("wildcard_match", _wildcard_match)
register_fallback("resolve_routes", _resolve_routes)
register_fallback("batch_resolve_routes", _batch_resolve_routes)
register_fallback("deduplicate_events", _deduplicate_events)
register_fallback("sort_by_priority", _sort_by_priority)

# Simulation (C1) — H-82: was missing
register_fallback("topological_sort", _topological_sort)
register_fallback("detect_cycles", _detect_cycles)
register_fallback("aggregate_impact", _aggregate_impact)
register_fallback("simulate_dag", _simulate_dag)

# Risk (F3) — H-82: was missing
register_fallback("calculate_blast_radius", _calculate_blast_radius)
register_fallback("propagate_risks", _propagate_risks)
register_fallback("find_critical_path", _find_critical_path)
register_fallback("compute_reachability", _compute_reachability)
register_fallback("multi_node_blast_radius", _multi_node_blast_radius)
