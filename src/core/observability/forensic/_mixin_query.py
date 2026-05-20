"""
forensic._mixin_query — Query and correlation helpers mixin for ForensicEngine.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.shared.db_initializer import get_connection, get_data_dir
from src.core.observability.forensic._types import ForensicEntry

logger = logging.getLogger(__name__)


class QueryMixin:
    """Mixin providing query/correlation helpers for ForensicEngine."""

    # These attributes are provided by the main class.
    _db_path: str

    def _get_audit_db_path(self) -> str:
        """Resolve the audit_log.sqlite path from the data directory."""
        return str(get_data_dir() / "audit_log.sqlite")

    def _load_audit_events(
        self, entity_id: str, tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """Load raw audit event rows for an entity from the audit DB."""
        db_path = self._get_audit_db_path()
        if not Path(db_path).exists():
            return []
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
            "SELECT * FROM audit_events "
            "WHERE tenant_id = ? "
            "  AND (metadata LIKE ? OR description LIKE ? OR event_id = ?) "
            "ORDER BY created_at ASC LIMIT 2000",
            (tenant_id, f"%{entity_id}%", f"%{entity_id}%", entity_id),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _load_ledger_entries(
        self, entity_id: str, tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """Load raw ledger rows for an entity."""
        conn = get_connection("merkle_ledger.sqlite")
        rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
        """Cross-correlate audit events and ledger entries."""
        entries: List[ForensicEntry] = []

        audit_by_trace: Dict[str, Dict[str, Any]] = {}
        for row in audit_rows:
            tid = row.get("trace_id") or ""
            if tid:
                audit_by_trace[tid] = row

        matched_audit_trace_ids: set[str] = set()

        for lrow in ledger_rows:
            ledger_ts: float = lrow.get("timestamp", 0.0) or 0.0
            matched_audit: Optional[Dict[str, Any]] = None

            for arow in audit_rows:
                audit_ts: float = arow.get("created_at", 0.0) or 0.0
                if abs(audit_ts - ledger_ts) <= 2.0:
                    audit_trace = arow.get("trace_id") or ""
                    if audit_trace and audit_trace in audit_by_trace:
                        if audit_by_trace[audit_trace] is arow:
                            matched_audit = arow
                            matched_audit_trace_ids.add(audit_trace)
                            break
                    if matched_audit is None:
                        matched_audit = arow
                        matched_audit_trace_ids.add(arow.get("trace_id") or "")

            if matched_audit is not None:
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
                entries.append(ForensicEntry(
                    source="ledger",
                    timestamp=datetime.fromtimestamp(
                        lrow.get("timestamp", 0.0) or 0.0, tz=timezone.utc
                    ).isoformat() if lrow.get("timestamp") else "",
                    timestamp_epoch=lrow.get("timestamp", 0.0) or 0.0,
                    entity_id=entity_id, tenant_id=tenant_id,
                    operation=lrow.get("operation", ""),
                    hash_sha256=lrow.get("hash_sha256", ""),
                    parent_hash=lrow.get("parent_hash", ""),
                ))

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

        entries.sort(key=lambda e: e.timestamp_epoch)
        return entries
