"""
ZENIC-AGENTS — Forensic Engine (A1: Enriched Audit + Forensic Audit).

Unifies MerkleLedger + AuditLogger + Tracing into a single query interface
for forensic analysis, chain verification, and evidence export.

This package re-exports every symbol from the original monolithic
``forensic.py`` so that ``from src.core.observability.forensic import X``
continues to work unchanged.
"""

# ── Re-export all public symbols ─────────────────────────────

from ._types import (
    ChainVerificationResult,
    EvidenceBundle,
    ForensicEntry,
    ForensicReport,
)

from ._engine import (
    ForensicEngine,
    get_forensic_engine,
    reset_forensic_engine,
)

# Also expose the internal submodules' public helpers for advanced use
from ._collector import (
    retry as _retry,
    RETRY_MAX_ATTEMPTS as _RETRY_MAX_ATTEMPTS,
    RETRY_BASE_DELAY as _RETRY_BASE_DELAY,
    get_audit_db_path as _get_audit_db_path,
    load_audit_events as _load_audit_events,
    load_ledger_entries as _load_ledger_entries,
    correlate as _correlate,
)

from ._analyzer import (
    verify_local_chain as _verify_local_chain,
    verify_chain_entries as _verify_chain_entries,
    build_merkle_proofs as _build_merkle_proofs,
    compute_merkle_root as _compute_merkle_root,
)

__all__ = [
    # Dataclasses
    "ForensicEntry",
    "ForensicReport",
    "ChainVerificationResult",
    "EvidenceBundle",
    # Engine
    "ForensicEngine",
    # Singleton
    "get_forensic_engine",
    "reset_forensic_engine",
]
