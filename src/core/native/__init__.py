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

Implementation is split across ``_native_parts/`` sub-modules for
maintainability; this file re-exports every public symbol so that
all original import paths remain valid.
"""

from __future__ import annotations

# Re-export every public symbol from the split sub-modules.
from ._native_parts import (  # noqa: F401
    # Feature flag
    HAS_NATIVE,
    # Lazy access helpers for PyO3 types
    get_native_module,
    get_encrypted_db,
    get_shared_memory_bus,
    get_safety_verdict,
    get_license_info,
    # Crypto
    argon2id_hash,
    constant_time_compare,
    pbkdf2_derive_key,
    # Hash
    blake3_hash,
    merkle_root,
    xxhash64,
    # Forensic (A1)
    batch_verify_chains,
    chain_hash,
    forensic_hash,
    merkle_proof,
    verify_merkle_chain,
    # Rollback (A3)
    file_hash,
    restore_file,
    snapshot_file,
    verify_rollback_readiness,
    # EventBus (B1)
    batch_resolve_routes,
    deduplicate_events,
    resolve_routes,
    sort_by_priority,
    wildcard_match,
    # Simulation (C1)
    aggregate_impact,
    detect_cycles,
    simulate_dag,
    topological_sort,
    # Risk (F3)
    calculate_blast_radius,
    compute_reachability,
    find_critical_path,
    multi_node_blast_radius,
    propagate_risks,
)

__all__ = [
    # Feature flag
    "HAS_NATIVE",
    # Lazy access helpers for PyO3 types
    "get_native_module",
    "get_encrypted_db",
    "get_shared_memory_bus",
    "get_safety_verdict",
    "get_license_info",
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
