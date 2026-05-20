"""
native._simulation — Dry-Run Simulation (C1) API functions.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List, Tuple

from src.core.native._bindings import HAS_NATIVE

if HAS_NATIVE:
    from src.core.native._bindings import (
        _rust_topological_sort,
        _rust_detect_cycles,
        _rust_aggregate_impact,
        _rust_simulate_dag,
    )


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
