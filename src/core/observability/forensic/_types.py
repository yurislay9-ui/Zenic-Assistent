"""
ZENIC-AGENTS — Forensic data types.

Dataclasses used throughout the forensic subsystem: entries, reports,
chain-verification results, and evidence bundles.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ForensicEntry:
    """A single entry in the forensic timeline.

    Represents either an audit event, a merkle ledger entry, or both
    when cross-correlation succeeds.
    """

    entry_id: str = ""
    source: str = ""  # "audit" | "ledger" | "correlated"
    timestamp: str = ""
    timestamp_epoch: float = 0.0
    entity_id: str = ""
    trace_id: str = ""
    span_id: str = ""
    tenant_id: str = ""
    event_type: str = ""
    severity: str = ""
    description: str = ""
    operation: str = ""
    hash_sha256: str = ""
    parent_hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.entry_id:
            self.entry_id = f"fentry-{uuid.uuid4().hex[:12]}"


@dataclass
class ForensicReport:
    """Result of a forensic_query call — a verified timeline for an entity."""

    report_id: str = ""
    entity_id: str = ""
    tenant_id: str = ""
    query_time: str = ""
    time_range: Optional[Tuple[float, float]] = None
    entries: List[ForensicEntry] = field(default_factory=list)
    total_audit_events: int = 0
    total_ledger_entries: int = 0
    correlated_count: int = 0
    chain_intact: bool = True

    def __post_init__(self) -> None:
        if not self.report_id:
            self.report_id = f"freport-{uuid.uuid4().hex[:12]}"
        if not self.query_time:
            self.query_time = datetime.now(timezone.utc).isoformat()


@dataclass
class ChainVerificationResult:
    """Result of verifying the Merkle chain integrity for a tenant."""

    tenant_id: str = ""
    verification_time: str = ""
    total_entries: int = 0
    valid_entries: int = 0
    broken_links: List[Dict[str, Any]] = field(default_factory=list)
    is_valid: bool = True
    root_hash: str = ""

    def __post_init__(self) -> None:
        if not self.verification_time:
            self.verification_time = datetime.now(timezone.utc).isoformat()


@dataclass
class EvidenceBundle:
    """A JSON-serializable package of all forensic data for an entity.

    Includes audit events, ledger entries, and merkle proofs.
    Suitable for compliance export or legal hold.
    """

    bundle_id: str = ""
    entity_id: str = ""
    tenant_id: str = ""
    export_time: str = ""
    audit_events: List[Dict[str, Any]] = field(default_factory=list)
    ledger_entries: List[Dict[str, Any]] = field(default_factory=list)
    merkle_proofs: List[Dict[str, Any]] = field(default_factory=list)
    chain_verification: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if not self.bundle_id:
            self.bundle_id = f"ebundle-{uuid.uuid4().hex[:12]}"
        if not self.export_time:
            self.export_time = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "bundle_id": self.bundle_id,
            "entity_id": self.entity_id,
            "tenant_id": self.tenant_id,
            "export_time": self.export_time,
            "audit_events": self.audit_events,
            "ledger_entries": self.ledger_entries,
            "merkle_proofs": self.merkle_proofs,
            "chain_verification": self.chain_verification,
        }

    def to_json(self) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str, indent=2)
