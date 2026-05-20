"""
ZENIC-AGENTS — Forensic data collector.

Provides the retry helper, database query functions, and the
cross-correlation logic used by the ForensicEngine.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.shared.db_initializer import get_connection, get_data_dir

from ._types import ForensicEntry

logger = logging.getLogger(__name__)

# ── Retry constants ──────────────────────────────────────────
RETRY_MAX_ATTEMPTS: int = 3
RETRY_BASE_DELAY: float = 1.0  # 1 second base


def retry(fn, label: str = "forensic_db_op"):
    """Execute *fn* with exponential backoff (3 retries, base 1 s)."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < RETRY_MAX_ATTEMPTS:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.debug(
                    "%s error (attempt %d/%d): %s — retrying in %.2fs",
                    label, attempt, RETRY_MAX_ATTEMPTS, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "%s failed after %d attempts: %s",
                    label, RETRY_MAX_ATTEMPTS, exc,
                )
    raise last_exc  # type: ignore[misc]


# ── DB path helpers ──────────────────────────────────────────

def get_audit_db_path() -> str:
    """Resolve the audit_log.sqlite path from the data directory."""
    return str(get_data_dir() / "audit_log.sqlite")


# ── Data loading ─────────────────────────────────────────────

def load_audit_events(
    entity_id: str,
    tenant_id: str,
    time_range: Optional[Tuple[float, float]] = None,
) -> List[Dict[str, Any]]:
    """Load raw audit event rows for an entity from the audit DB.

    Args:
        entity_id: Entity identifier to search for.
        tenant_id: Tenant scope.
        time_range: Optional (start_epoch, end_epoch) window.

    Returns:
        List of row dicts ordered by created_at ascending.
    """
    db_path = get_audit_db_path()
    if not Path(db_path).exists():
        return []

    def _query() -> List[Dict[str, Any]]:
        conn = sqlite3.connect(db_path)
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

    return retry(_query, label="load_audit_events")


def load_ledger_entries(
    entity_id: str,
    tenant_id: str,
    time_range: Optional[Tuple[float, float]] = None,
) -> List[Dict[str, Any]]:
    """Load raw ledger rows for an entity.

    Args:
        entity_id: Entity identifier (maps to file_path in ledger).
        tenant_id: Tenant scope.
        time_range: Optional (start_epoch, end_epoch) window.

    Returns:
        List of row dicts ordered by id ascending.
    """

    def _query() -> List[Dict[str, Any]]:
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
            "ORDER BY id ASC LIMIT 2000",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    return retry(_query, label="load_ledger_entries")


# ── Cross-correlation ────────────────────────────────────────

def correlate(
    audit_rows: List[Dict[str, Any]],
    ledger_rows: List[Dict[str, Any]],
    entity_id: str,
    tenant_id: str,
) -> List[ForensicEntry]:
    """Cross-correlate audit events and ledger entries.

    Strategy:
    1. Build a trace_id -> audit_row index.
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

        # Search for audit events within +/- 2 seconds of the ledger timestamp
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
