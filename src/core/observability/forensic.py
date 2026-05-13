"""
ZENIC-AGENTS — Forensic Engine (A1: Enriched Audit + Forensic Audit).

Unifies MerkleLedger + AuditLogger + Tracing into a single query interface
for forensic analysis, chain verification, and evidence export.

Features:
- Cross-correlation of audit events and merkle ledger entries by trace_id / timestamp
- Merkle chain integrity verification with detailed break reporting
- JSON-serializable evidence bundle export for compliance / legal hold
- Every DB operation wrapped in retry with exponential backoff (3 retries, base 1s)
- Thread-safe via threading.RLock
- SQLite persistence for forensic query audit trail
- Singleton pattern with get_forensic_engine() / reset_forensic_engine()
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.shared.db_initializer import get_connection, get_data_dir
from src.core.native import (
    forensic_hash as _native_forensic_hash,
    chain_hash as _native_chain_hash,
    verify_merkle_chain as _native_verify_merkle_chain,
    merkle_proof as _native_merkle_proof,
    batch_verify_chains as _native_batch_verify_chains,
    HAS_NATIVE as _HAS_NATIVE,
)

logger = logging.getLogger(__name__)

# ── Retry constants ──────────────────────────────────────────
_RETRY_MAX_ATTEMPTS: int = 3
_RETRY_BASE_DELAY: float = 1.0  # 1 second base


# ── Dataclasses ──────────────────────────────────────────────

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


# ── Retry helper ─────────────────────────────────────────────

def _retry(fn, label: str = "forensic_db_op"):
    """Execute *fn* with exponential backoff (3 retries, base 1 s)."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < _RETRY_MAX_ATTEMPTS:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.debug(
                    "%s error (attempt %d/%d): %s — retrying in %.2fs",
                    label, attempt, _RETRY_MAX_ATTEMPTS, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "%s failed after %d attempts: %s",
                    label, _RETRY_MAX_ATTEMPTS, exc,
                )
    raise last_exc  # type: ignore[misc]


# ── ForensicEngine ───────────────────────────────────────────

class ForensicEngine:
    """Unified forensic query interface over AuditLogger + MerkleLedger + Tracing.

    Thread-safe.  All DB operations are retried with exponential backoff.
    Records every forensic query in its own SQLite DB for auditability.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            db_path = str(get_data_dir() / "forensic_queries.sqlite")
        self._db_path = db_path
        self._lock = threading.RLock()
        self._initialized = False
        self._init_db()

    # ── DB bootstrap ─────────────────────────────────────

    def _init_db(self) -> None:
        """Create the forensic_queries SQLite schema."""

        def _create() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS forensic_queries (
                    query_id TEXT PRIMARY KEY,
                    query_type TEXT NOT NULL,
                    entity_id TEXT,
                    tenant_id TEXT NOT NULL,
                    time_range_start REAL,
                    time_range_end REAL,
                    result_summary TEXT,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fq_tenant
                ON forensic_queries(tenant_id, created_at DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fq_entity
                ON forensic_queries(entity_id)
            """)
            conn.commit()
            conn.close()

        try:
            _retry(_create, label="ForensicEngine._init_db")
            self._initialized = True
            logger.info("ForensicEngine: Database initialized at %s", self._db_path)
        except Exception as exc:
            logger.error("ForensicEngine: Database initialization failed: %s", exc)
            self._initialized = False

    # ── Public API ───────────────────────────────────────

    def forensic_query(
        self,
        entity_id: str,
        time_range: Optional[Tuple[float, float]],
        tenant_id: str,
    ) -> ForensicReport:
        """Query audit events + ledger entries for an entity and cross-correlate.

        Args:
            entity_id: The entity to query (maps to file_path in ledger,
                       searched in audit metadata / description).
            time_range: Optional (start_epoch, end_epoch) window.
            tenant_id: Tenant scope.

        Returns:
            ForensicReport with a verified, chronologically sorted timeline.
        """
        logger.info(
            "ForensicEngine: forensic_query entity=%s tenant=%s range=%s",
            entity_id, tenant_id, time_range,
        )

        audit_rows: List[Dict[str, Any]] = []
        ledger_rows: List[Dict[str, Any]] = []

        # --- Query audit events ---
        def _query_audit() -> List[Dict[str, Any]]:
            conn = sqlite3.connect(self._get_audit_db_path())
            conn.row_factory = sqlite3.Row
            conditions = ["tenant_id = ?"]
            params: List[Any] = [tenant_id]

            # Search by entity_id in metadata JSON or description
            conditions.append(
                "(metadata LIKE ? OR description LIKE ? OR event_id = ?)"
            )
            params.append(f"%{entity_id}%")
            params.append(f"%{entity_id}%")
            params.append(entity_id)

            if time_range is not None:
                conditions.append("created_at >= ?")
                params.append(time_range[0])
                conditions.append("created_at <= ?")
                params.append(time_range[1])

            where = " AND ".join(conditions)
            rows = conn.execute(
                f"SELECT * FROM audit_events WHERE {where} "
                "ORDER BY created_at ASC LIMIT 2000",
                params,
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

        try:
            audit_rows = _retry(_query_audit, label="forensic_query.audit")
        except Exception as exc:
            logger.error("ForensicEngine: audit query failed: %s", exc)

        # --- Query merkle ledger ---
        def _query_ledger() -> List[Dict[str, Any]]:
            conn = get_connection("merkle_ledger.sqlite")
            conditions = ["tenant_id = ?"]
            params: List[Any] = [tenant_id]

            # file_path acts as entity identifier in the ledger
            conditions.append("file_path = ?")
            params.append(entity_id)

            if time_range is not None:
                conditions.append("timestamp >= ?")
                params.append(time_range[0])
                conditions.append("timestamp <= ?")
                params.append(time_range[1])

            where = " AND ".join(conditions)
            rows = conn.execute(
                f"SELECT * FROM ledger WHERE {where} "
                "ORDER BY timestamp ASC LIMIT 2000",
                params,
            ).fetchall()
            return [dict(r) for r in rows]

        try:
            ledger_rows = _retry(_query_ledger, label="forensic_query.ledger")
        except Exception as exc:
            logger.error("ForensicEngine: ledger query failed: %s", exc)

        # --- Cross-correlate ---
        entries = self._correlate(audit_rows, ledger_rows, entity_id, tenant_id)

        # --- Verify chain integrity for the returned ledger entries ---
        chain_intact = self._verify_local_chain(ledger_rows)

        report = ForensicReport(
            entity_id=entity_id,
            tenant_id=tenant_id,
            time_range=time_range,
            entries=entries,
            total_audit_events=len(audit_rows),
            total_ledger_entries=len(ledger_rows),
            correlated_count=sum(1 for e in entries if e.source == "correlated"),
            chain_intact=chain_intact,
        )

        # --- Persist query record ---
        self._record_query(
            query_id=report.report_id,
            query_type="forensic_query",
            entity_id=entity_id,
            tenant_id=tenant_id,
            time_range=time_range,
            result_summary=(
                f"audit={len(audit_rows)} ledger={len(ledger_rows)} "
                f"correlated={report.correlated_count} chain_ok={chain_intact}"
            ),
        )

        logger.info(
            "ForensicEngine: forensic_query complete — report=%s entries=%d",
            report.report_id, len(entries),
        )
        return report

    def verify_chain(self, tenant_id: str) -> ChainVerificationResult:
        """Verify Merkle chain integrity for all ledger entries of a tenant.

        Walks the ledger chronologically and checks that every entry's
        parent_hash matches the preceding entry's hash_sha256.  Breaks
        are recorded with full details.

        Args:
            tenant_id: Tenant whose ledger chain to verify.

        Returns:
            ChainVerificationResult with validity status and break details.
        """
        logger.info("ForensicEngine: verify_chain tenant=%s", tenant_id)

        ledger_rows: List[Dict[str, Any]] = []

        def _load() -> List[Dict[str, Any]]:
            conn = get_connection("merkle_ledger.sqlite")
            rows = conn.execute(
                "SELECT id, file_path, hash_sha256, parent_hash, operation, timestamp "
                "FROM ledger WHERE tenant_id = ? ORDER BY id ASC",
                (tenant_id,),
            ).fetchall()
            return [dict(r) for r in rows]

        try:
            ledger_rows = _retry(_load, label="verify_chain.load")
        except Exception as exc:
            logger.error("ForensicEngine: verify_chain load failed: %s", exc)
            return ChainVerificationResult(
                tenant_id=tenant_id,
                total_entries=0,
                valid_entries=0,
                is_valid=False,
            )

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

        result = ChainVerificationResult(
            tenant_id=tenant_id,
            total_entries=total,
            valid_entries=valid_count,
            broken_links=broken_links,
            is_valid=is_valid,
            root_hash=root_hash,
        )

        # --- Persist query record ---
        self._record_query(
            query_id=f"chain-{uuid.uuid4().hex[:12]}",
            query_type="verify_chain",
            entity_id="",
            tenant_id=tenant_id,
            time_range=None,
            result_summary=(
                f"total={total} valid={valid_count} "
                f"broken={len(broken_links)} ok={is_valid}"
            ),
        )

        logger.info(
            "ForensicEngine: verify_chain complete — valid=%s total=%d broken=%d",
            is_valid, total, len(broken_links),
        )
        return result

    def export_evidence_bundle(
        self,
        entity_id: str,
        tenant_id: str,
    ) -> EvidenceBundle:
        """Package all forensic data for an entity into a JSON-serializable bundle.

        Includes audit events, ledger entries, merkle proofs, and chain
        verification status.

        Args:
            entity_id: Entity to export.
            tenant_id: Tenant scope.

        Returns:
            EvidenceBundle ready for to_json() or to_dict().
        """
        logger.info(
            "ForensicEngine: export_evidence_bundle entity=%s tenant=%s",
            entity_id, tenant_id,
        )

        # Gather audit events
        audit_events: List[Dict[str, Any]] = []
        try:
            audit_events = _retry(
                lambda: self._load_audit_events(entity_id, tenant_id),
                label="export.audit",
            )
        except Exception as exc:
            logger.error("ForensicEngine: export audit load failed: %s", exc)

        # Gather ledger entries
        ledger_entries: List[Dict[str, Any]] = []
        try:
            ledger_entries = _retry(
                lambda: self._load_ledger_entries(entity_id, tenant_id),
                label="export.ledger",
            )
        except Exception as exc:
            logger.error("ForensicEngine: export ledger load failed: %s", exc)

        # Build merkle proofs
        merkle_proofs = self._build_merkle_proofs(ledger_entries)

        # Chain verification
        chain_result = self.verify_chain(tenant_id)
        chain_dict = {
            "is_valid": chain_result.is_valid,
            "total_entries": chain_result.total_entries,
            "valid_entries": chain_result.valid_entries,
            "root_hash": chain_result.root_hash,
            "broken_links": chain_result.broken_links,
            "verification_time": chain_result.verification_time,
        }

        bundle = EvidenceBundle(
            entity_id=entity_id,
            tenant_id=tenant_id,
            audit_events=audit_events,
            ledger_entries=ledger_entries,
            merkle_proofs=merkle_proofs,
            chain_verification=chain_dict,
        )

        # Persist query record
        self._record_query(
            query_id=bundle.bundle_id,
            query_type="export_evidence_bundle",
            entity_id=entity_id,
            tenant_id=tenant_id,
            time_range=None,
            result_summary=(
                f"audit={len(audit_events)} ledger={len(ledger_entries)} "
                f"proofs={len(merkle_proofs)} chain_ok={chain_result.is_valid}"
            ),
        )

        logger.info(
            "ForensicEngine: export_evidence_bundle complete — bundle=%s",
            bundle.bundle_id,
        )
        return bundle

    # ── Internal helpers ─────────────────────────────────

    def _get_audit_db_path(self) -> str:
        """Resolve the audit_log.sqlite path from the data directory."""
        return str(get_data_dir() / "audit_log.sqlite")

    def _load_audit_events(
        self,
        entity_id: str,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """Load raw audit event rows for an entity from the audit DB."""
        db_path = self._get_audit_db_path()
        if not Path(db_path).exists():
            return []
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM audit_events "
            "WHERE tenant_id = ? "
            "  AND (metadata LIKE ? OR description LIKE ? OR event_id = ?) "
            "ORDER BY created_at ASC LIMIT 2000",
            (tenant_id, f"%{entity_id}%", f"%{entity_id}%", entity_id),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _load_ledger_entries(
        self,
        entity_id: str,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """Load raw ledger rows for an entity."""
        conn = get_connection("merkle_ledger.sqlite")
        rows = conn.execute(
            "SELECT * FROM ledger "
            "WHERE tenant_id = ? AND file_path = ? "
            "ORDER BY id ASC LIMIT 2000",
            (tenant_id, entity_id),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _correlate(
        audit_rows: List[Dict[str, Any]],
        ledger_rows: List[Dict[str, Any]],
        entity_id: str,
        tenant_id: str,
    ) -> List[ForensicEntry]:
        """Cross-correlate audit events and ledger entries.

        Strategy:
        1. Build a trace_id → audit_row index.
        2. Walk ledger rows; if a ledger entry has a trace_id match
           in the audit index, emit a "correlated" ForensicEntry.
        3. Emit unmatched audit rows as "audit" entries.
        4. Emit unmatched ledger rows as "ledger" entries.
        5. Sort everything by timestamp_epoch ascending.
        """
        entries: List[ForensicEntry] = []

        # Index audit rows by trace_id
        audit_by_trace: Dict[str, Dict[str, Any]] = {}
        for row in audit_rows:
            tid = row.get("trace_id") or ""
            if tid:
                audit_by_trace[tid] = row

        matched_audit_trace_ids: set[str] = set()

        # Walk ledger rows
        for lrow in ledger_rows:
            ledger_trace = str(lrow.get("id", ""))  # ledger has no trace_id natively
            # Try to find an audit event with matching timestamp proximity
            matched_audit: Optional[Dict[str, Any]] = None
            ledger_ts: float = lrow.get("timestamp", 0.0) or 0.0

            # Search for audit events within ±2 seconds of the ledger timestamp
            for arow in audit_rows:
                audit_ts: float = arow.get("created_at", 0.0) or 0.0
                if abs(audit_ts - ledger_ts) <= 2.0:
                    # Check trace_id overlap
                    audit_trace = arow.get("trace_id") or ""
                    if audit_trace and audit_trace in audit_by_trace:
                        if audit_by_trace[audit_trace] is arow:
                            matched_audit = arow
                            matched_audit_trace_ids.add(audit_trace)
                            break
                    # Also match by timestamp proximity alone if no trace overlap
                    if matched_audit is None:
                        matched_audit = arow
                        matched_audit_trace_ids.add(arow.get("trace_id") or "")

            if matched_audit is not None:
                # Correlated entry
                meta_raw = matched_audit.get("metadata") or "{}"
                if isinstance(meta_raw, str):
                    try:
                        meta = json.loads(meta_raw)
                    except (json.JSONDecodeError, TypeError):
                        meta = {"raw": meta_raw}
                else:
                    meta = meta_raw

                entries.append(ForensicEntry(
                    source="correlated",
                    timestamp=matched_audit.get("timestamp", ""),
                    timestamp_epoch=matched_audit.get("created_at", 0.0) or 0.0,
                    entity_id=entity_id,
                    trace_id=matched_audit.get("trace_id", ""),
                    span_id=matched_audit.get("span_id", ""),
                    tenant_id=tenant_id,
                    event_type=matched_audit.get("event_type", ""),
                    severity=matched_audit.get("severity", ""),
                    description=matched_audit.get("description", ""),
                    operation=lrow.get("operation", ""),
                    hash_sha256=lrow.get("hash_sha256", ""),
                    parent_hash=lrow.get("parent_hash", ""),
                    metadata=meta,
                ))
            else:
                # Ledger-only entry
                entries.append(ForensicEntry(
                    source="ledger",
                    timestamp=datetime.fromtimestamp(
                        lrow.get("timestamp", 0.0) or 0.0, tz=timezone.utc
                    ).isoformat() if lrow.get("timestamp") else "",
                    timestamp_epoch=lrow.get("timestamp", 0.0) or 0.0,
                    entity_id=entity_id,
                    tenant_id=tenant_id,
                    operation=lrow.get("operation", ""),
                    hash_sha256=lrow.get("hash_sha256", ""),
                    parent_hash=lrow.get("parent_hash", ""),
                ))

        # Unmatched audit rows
        for arow in audit_rows:
            trace_id = arow.get("trace_id") or ""
            if trace_id in matched_audit_trace_ids:
                continue
            meta_raw = arow.get("metadata") or "{}"
            if isinstance(meta_raw, str):
                try:
                    meta = json.loads(meta_raw)
                except (json.JSONDecodeError, TypeError):
                    meta = {"raw": meta_raw}
            else:
                meta = meta_raw

            entries.append(ForensicEntry(
                source="audit",
                timestamp=arow.get("timestamp", ""),
                timestamp_epoch=arow.get("created_at", 0.0) or 0.0,
                entity_id=entity_id,
                trace_id=trace_id,
                span_id=arow.get("span_id", ""),
                tenant_id=tenant_id,
                event_type=arow.get("event_type", ""),
                severity=arow.get("severity", ""),
                description=arow.get("description", ""),
                metadata=meta,
            ))

        # Sort by timestamp_epoch ascending
        entries.sort(key=lambda e: e.timestamp_epoch)
        return entries

    @staticmethod
    def _verify_local_chain(ledger_rows: List[Dict[str, Any]]) -> bool:
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

    @staticmethod
    def _build_merkle_proofs(
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
            root = ForensicEngine._compute_merkle_root(all_hashes)

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

    @staticmethod
    def _compute_merkle_root(hashes: List[str]) -> str:
        """Compute a Merkle root hash from a list of leaf hashes.

        Delegates to the Rust native extension when available for
        BLAKE3-based Merkle root computation. Falls back to SHA-256
        pure Python when the extension is not compiled.
        """
        from src.core.native import merkle_root as _native_merkle_root_fn

        if not hashes:
            import hashlib
            return hashlib.sha256(b"empty").hexdigest()
        if len(hashes) == 1:
            return hashes[0]

        if _HAS_NATIVE:
            try:
                return _native_merkle_root_fn([h.encode() for h in hashes])
            except Exception:
                pass  # Fall through to pure Python

        import hashlib
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

    # ── Persistence helpers ──────────────────────────────

    def _record_query(
        self,
        query_id: str,
        query_type: str,
        entity_id: str,
        tenant_id: str,
        time_range: Optional[Tuple[float, float]],
        result_summary: str,
    ) -> None:
        """Persist a record of a forensic query to SQLite."""
        if not self._initialized:
            return

        def _insert() -> None:
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    """INSERT INTO forensic_queries
                       (query_id, query_type, entity_id, tenant_id,
                        time_range_start, time_range_end, result_summary, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        query_id,
                        query_type,
                        entity_id,
                        tenant_id,
                        time_range[0] if time_range else None,
                        time_range[1] if time_range else None,
                        result_summary,
                        time.time(),
                    ),
                )
                conn.commit()
                conn.close()

        try:
            _retry(_insert, label="ForensicEngine._record_query")
        except Exception as exc:
            logger.error("ForensicEngine: failed to record query: %s", exc)


# ── Singleton ────────────────────────────────────────────────

_forensic_engine_instance: Optional[ForensicEngine] = None
_forensic_engine_lock = threading.Lock()


def get_forensic_engine(db_path: Optional[str] = None) -> ForensicEngine:
    """Get or create the singleton ForensicEngine.

    Args:
        db_path: Optional custom SQLite path for the forensic queries DB.

    Returns:
        The shared ForensicEngine instance.
    """
    global _forensic_engine_instance
    with _forensic_engine_lock:
        if _forensic_engine_instance is None:
            _forensic_engine_instance = ForensicEngine(db_path=db_path)
        return _forensic_engine_instance


def reset_forensic_engine() -> None:
    """Reset the singleton ForensicEngine (for testing / reconfiguration)."""
    global _forensic_engine_instance
    with _forensic_engine_lock:
        _forensic_engine_instance = None
    logger.info("ForensicEngine: singleton reset")


# ── Module exports ───────────────────────────────────────────

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
