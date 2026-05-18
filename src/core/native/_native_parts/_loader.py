"""
Native extension loader and lazy PyO3 access helpers.

Detects the ``_zenic_native`` Rust extension and exposes:
- ``HAS_NATIVE`` flag
- ``_rust_*`` prefixed native function references
- Lazy accessor functions for PyO3 types (EncryptedDb, SharedMemoryBus, etc.)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

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
# Lazy access to extended PyO3 modules (db, bus, safety_gate, license)
# These are available when HAS_NATIVE=True but not imported eagerly
# to avoid hard dependency on the Rust extension.
# ---------------------------------------------------------------------------

def get_native_module() -> Optional[Any]:
    """Return the _zenic_native module if available, else None.

    Use this for lazy access to PyO3 types like EncryptedDb,
    SharedMemoryBus, SafetyVerdict, LicenseInfo, etc.
    """
    if not HAS_NATIVE:
        return None
    try:
        import _zenic_native as _mod  # type: ignore[import-not-found]
        return _mod
    except ImportError:
        return None


def get_encrypted_db() -> Optional[type]:
    """Return the EncryptedDb PyO3 class if native extension is available."""
    _mod = get_native_module()
    if _mod is None:
        return None
    return getattr(_mod, "EncryptedDb", None)


def get_shared_memory_bus() -> Optional[type]:
    """Return the SharedMemoryBus PyO3 class if native extension is available."""
    _mod = get_native_module()
    if _mod is None:
        return None
    return getattr(_mod, "SharedMemoryBus", None)


def get_safety_verdict() -> Optional[type]:
    """Return the SafetyVerdict PyO3 enum if native extension is available."""
    _mod = get_native_module()
    if _mod is None:
        return None
    return getattr(_mod, "SafetyVerdict", None)


def get_license_info() -> Optional[type]:
    """Return the LicenseInfo PyO3 class if native extension is available."""
    _mod = get_native_module()
    if _mod is None:
        return None
    return getattr(_mod, "LicenseInfo", None)
