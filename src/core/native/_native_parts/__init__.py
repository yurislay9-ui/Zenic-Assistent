"""
Internal split modules for ``src.core.native``.

This package is not part of the public API — all symbols are re-exported
by the parent ``native/__init__.py``.
"""

from ._loader import (
    HAS_NATIVE,
    get_native_module,
    get_encrypted_db,
    get_shared_memory_bus,
    get_safety_verdict,
    get_license_info,
)
from ._crypto import (
    pbkdf2_derive_key,
    argon2id_hash,
    constant_time_compare,
    blake3_hash,
    xxhash64,
    merkle_root,
)
from ._forensic import (
    forensic_hash,
    chain_hash,
    verify_merkle_chain,
    merkle_proof,
    batch_verify_chains,
)
from ._rollback import (
    snapshot_file,
    restore_file,
    verify_rollback_readiness,
    file_hash,
)
from ._eventbus import (
    wildcard_match,
    resolve_routes,
    batch_resolve_routes,
    deduplicate_events,
    sort_by_priority,
)
from ._simulation import (
    topological_sort,
    detect_cycles,
    aggregate_impact,
    simulate_dag,
)
from ._risk import (
    calculate_blast_radius,
    propagate_risks,
    find_critical_path,
    compute_reachability,
    multi_node_blast_radius,
)
