"""
forensic._mixin_core — Core public API mixin for ForensicEngine.
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.shared.db_initializer import get_connection, get_data_dir
from src.core.native import HAS_NATIVE as _HAS_NATIVE
from src.core.observability.forensic._types import (
    ChainVerificationResult,
    EvidenceBundle,
    ForensicEntry,
    ForensicReport,
)
from src.core.observability.forensic._helpers import (
    retry as _retry,
    verify_local_chain,
    build_merkle_proofs,
)

logger = logging.getLogger(__name__)


class CoreMixin:
    """Mixin providing core public API for ForensicEngine."""

    # These attributes are provided by the main class.
    _db_path: str
    _lock: object
    _initialized: bool

    # ── DB bootstrap ─────────────────────────────────────

    def _init_db(self) -> None:
        """Create the forensic_queries SQLite schema."""

        def _create() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
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
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_fq_tenant
                ON forensic_queries(tenant_id, created_at DESC)
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
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
        """Query audit events + ledger entries for an entity and cross-correlate."""
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
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
            conditions.append("file_path = ?")
            params.append(entity_id)
            if time_range is not None:
                conditions.append("timestamp >= ?")
                params.append(time_range[0])
                conditions.append("timestamp <= ?")
                params.append(time_range[1])
            where = " AND ".join(conditions)
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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

        # --- Verify chain integrity ---
        chain_intact = verify_local_chain(ledger_rows)

        report = ForensicReport(
            entity_id=entity_id, tenant_id=tenant_id,
            time_range=time_range, entries=entries,
            total_audit_events=len(audit_rows),
            total_ledger_entries=len(ledger_rows),
            correlated_count=sum(1 for e in entries if e.source == "correlated"),
            chain_intact=chain_intact,
        )

        self._record_query(
            query_id=report.report_id, query_type="forensic_query",
            entity_id=entity_id, tenant_id=tenant_id,
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
        """Verify Merkle chain integrity for all ledger entries of a tenant."""
        logger.info("ForensicEngine: verify_chain tenant=%s", tenant_id)

        ledger_rows: List[Dict[str, Any]] = []

        def _load() -> List[Dict[str, Any]]:
            conn = get_connection("merkle_ledger.sqlite")
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
                tenant_id=tenant_id, total_entries=0, valid_entries=0, is_valid=False,
            )

        broken_links: List[Dict[str, Any]] = []
        valid_count = 0
        hash_to_id: Dict[str, int] = {r["hash_sha256"]: r["id"] for r in ledger_rows}

        file_groups: Dict[str, List[Dict[str, Any]]] = {}
        for r in ledger_rows:
            file_groups.setdefault(r["file_path"], []).append(r)

        for fp, group in file_groups.items():
            for i, row in enumerate(group):
                if row["parent_hash"] == "GENESIS":
                    valid_count += 1
                    continue
                expected_parent_hash = ""
                if i > 0:
                    expected_parent_hash = group[i - 1]["hash_sha256"]
                else:
                    expected_parent_hash = row["parent_hash"]
                    if row["parent_hash"] in hash_to_id:
                        valid_count += 1
                        continue
                if row["parent_hash"] == expected_parent_hash:
                    valid_count += 1
                else:
                    broken_links.append({
                        "file_path": fp, "entry_id": row["id"],
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
            tenant_id=tenant_id, total_entries=total,
            valid_entries=valid_count, broken_links=broken_links,
            is_valid=is_valid, root_hash=root_hash,
        )

        self._record_query(
            query_id=f"chain-{uuid.uuid4().hex[:12]}",
            query_type="verify_chain", entity_id="",
            tenant_id=tenant_id, time_range=None,
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
        self, entity_id: str, tenant_id: str,
    ) -> EvidenceBundle:
        """Package all forensic data for an entity into a JSON-serializable bundle."""
        logger.info(
            "ForensicEngine: export_evidence_bundle entity=%s tenant=%s",
            entity_id, tenant_id,
        )

        audit_events: List[Dict[str, Any]] = []
        try:
            audit_events = _retry(
                lambda: self._load_audit_events(entity_id, tenant_id),
                label="export.audit",
            )
        except Exception as exc:
            logger.error("ForensicEngine: export audit load failed: %s", exc)

        ledger_entries: List[Dict[str, Any]] = []
        try:
            ledger_entries = _retry(
                lambda: self._load_ledger_entries(entity_id, tenant_id),
                label="export.ledger",
            )
        except Exception as exc:
            logger.error("ForensicEngine: export ledger load failed: %s", exc)

        merkle_proofs = build_merkle_proofs(ledger_entries)
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
            entity_id=entity_id, tenant_id=tenant_id,
            audit_events=audit_events, ledger_entries=ledger_entries,
            merkle_proofs=merkle_proofs, chain_verification=chain_dict,
        )

        self._record_query(
            query_id=bundle.bundle_id, query_type="export_evidence_bundle",
            entity_id=entity_id, tenant_id=tenant_id, time_range=None,
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
