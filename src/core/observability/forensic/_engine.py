"""
ZENIC-AGENTS — Forensic engine.

The main ForensicEngine class that ties together collection, analysis,
and reporting.  Also provides the singleton accessors.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from src.core.shared.db_initializer import get_connection, get_data_dir

from ._analyzer import (
    build_merkle_proofs,
    compute_merkle_root,
    verify_chain_entries,
    verify_local_chain,
)
from ._collector import (
    correlate,
    get_audit_db_path,
    load_audit_events,
    load_ledger_entries,
    retry,
)
from ._types import (
    ChainVerificationResult,
    EvidenceBundle,
    ForensicEntry,
    ForensicReport,
)

logger = logging.getLogger(__name__)


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
            retry(_create, label="ForensicEngine._init_db")
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
        try:
            audit_rows = load_audit_events(entity_id, tenant_id, time_range)
        except Exception as exc:
            logger.error("ForensicEngine: audit query failed: %s", exc)

        # --- Query merkle ledger ---
        try:
            ledger_rows = load_ledger_entries(entity_id, tenant_id, time_range)
        except Exception as exc:
            logger.error("ForensicEngine: ledger query failed: %s", exc)

        # --- Cross-correlate ---
        entries = correlate(audit_rows, ledger_rows, entity_id, tenant_id)

        # --- Verify chain integrity for the returned ledger entries ---
        chain_intact = verify_local_chain(ledger_rows)

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
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT id, file_path, hash_sha256, parent_hash, operation, timestamp "
                "FROM ledger WHERE tenant_id = ? ORDER BY id ASC",
                (tenant_id,),
            ).fetchall()
            return [dict(r) for r in rows]

        try:
            ledger_rows = retry(_load, label="verify_chain.load")
        except Exception as exc:
            logger.error("ForensicEngine: verify_chain load failed: %s", exc)
            return ChainVerificationResult(
                tenant_id=tenant_id,
                total_entries=0,
                valid_entries=0,
                is_valid=False,
            )

        result = verify_chain_entries(ledger_rows, tenant_id)

        # --- Persist query record ---
        self._record_query(
            query_id=f"chain-{uuid.uuid4().hex[:12]}",
            query_type="verify_chain",
            entity_id="",
            tenant_id=tenant_id,
            time_range=None,
            result_summary=(
                f"total={result.total_entries} valid={result.valid_entries} "
                f"broken={len(result.broken_links)} ok={result.is_valid}"
            ),
        )

        logger.info(
            "ForensicEngine: verify_chain complete — valid=%s total=%d broken=%d",
            result.is_valid, result.total_entries, len(result.broken_links),
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
            audit_events = retry(
                lambda: load_audit_events(entity_id, tenant_id),
                label="export.audit",
            )
        except Exception as exc:
            logger.error("ForensicEngine: export audit load failed: %s", exc)

        # Gather ledger entries
        ledger_entries: List[Dict[str, Any]] = []
        try:
            ledger_entries = retry(
                lambda: load_ledger_entries(entity_id, tenant_id),
                label="export.ledger",
            )
        except Exception as exc:
            logger.error("ForensicEngine: export ledger load failed: %s", exc)

        # Build merkle proofs
        merkle_proofs = build_merkle_proofs(ledger_entries)

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
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
            retry(_insert, label="ForensicEngine._record_query")
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
