"""
ZENIC-AGENTS - Impact Preview Engine (A2: Pre-action Validation Enhancement)

Simulates the effects of an action WITHOUT executing it, providing
a preview of what would happen if the action were carried out.

All operations are strictly READ-ONLY — this engine never modifies data.

Uses SafetyGate and ActionCategory from safety_gate to classify actions
for preview routing, ensuring the preview respects the same risk taxonomy
as the execution pipeline.

Retry logic: DB operations wrapped with 3 retries, base 0.5s backoff.
Thread-safety: All public methods guarded by RLock.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .safety_gate import SafetyGate, ActionCategory, get_default_safety_gate

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  RISK LEVEL
# ──────────────────────────────────────────────────────────────

class ImpactRiskLevel(str, Enum):
    """Risk level of a previewed impact."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ──────────────────────────────────────────────────────────────
#  DATACLASSES
# ──────────────────────────────────────────────────────────────

@dataclass
class ImpactField:
    """A single field that would be affected by an action."""
    name: str
    current_value: Any = None
    proposed_value: Any = None
    field_type: str = "unknown"  # e.g. "str", "int", "bool"
    changed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
            "field_type": self.field_type,
            "changed": self.changed,
        }


@dataclass
class ImpactPreview:
    """General impact preview for any action type.

    Contains the high-level summary of what would happen if
    the action were executed, including risk assessment and
    affected resources.
    """
    action_type: str
    category: ActionCategory
    risk_level: ImpactRiskLevel
    risk_score: float
    summary: str
    affected_resources: List[str] = field(default_factory=list)
    fields: List[ImpactField] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    reversible: bool = True
    read_only: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "action_type": self.action_type,
            "category": self.category.value,
            "risk_level": self.risk_level.value,
            "risk_score": self.risk_score,
            "summary": self.summary,
            "affected_resources": self.affected_resources,
            "fields": [f.to_dict() for f in self.fields],
            "warnings": self.warnings,
            "reversible": self.reversible,
            "read_only": self.read_only,
            "metadata": self.metadata,
        }


@dataclass
class DBImpactPreview:
    """Impact preview specific to database operations.

    For DELETE: counts matching rows using SELECT COUNT(*) with same WHERE.
    For UPDATE: shows before->after diff.
    For INSERT: validates constraints.
    """
    operation: str                          # "SELECT", "INSERT", "UPDATE", "DELETE"
    table: str
    affected_rows: int = 0
    estimated_rows: int = 0                 # For DELETE: COUNT(*) with same WHERE
    fields: List[ImpactField] = field(default_factory=list)
    constraints_valid: bool = True
    constraint_violations: List[str] = field(default_factory=list)
    risk_level: ImpactRiskLevel = ImpactRiskLevel.NONE
    risk_score: float = 0.0
    summary: str = ""
    reversible: bool = True
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "operation": self.operation,
            "table": self.table,
            "affected_rows": self.affected_rows,
            "estimated_rows": self.estimated_rows,
            "fields": [f.to_dict() for f in self.fields],
            "constraints_valid": self.constraints_valid,
            "constraint_violations": self.constraint_violations,
            "risk_level": self.risk_level.value,
            "risk_score": self.risk_score,
            "summary": self.summary,
            "reversible": self.reversible,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


@dataclass
class FileImpactPreview:
    """Impact preview specific to file operations.

    Shows files affected, sizes, and whether they exist.
    """
    operation: str                          # "read", "write", "append", "delete", "copy", "move"
    source: str = ""
    destination: str = ""
    source_exists: bool = False
    destination_exists: bool = False
    source_size: int = 0
    destination_size: int = 0
    source_is_dir: bool = False
    destination_is_dir: bool = False
    would_overwrite: bool = False
    would_create: bool = False
    would_delete: bool = False
    risk_level: ImpactRiskLevel = ImpactRiskLevel.NONE
    risk_score: float = 0.0
    summary: str = ""
    reversible: bool = True
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "operation": self.operation,
            "source": self.source,
            "destination": self.destination,
            "source_exists": self.source_exists,
            "destination_exists": self.destination_exists,
            "source_size": self.source_size,
            "destination_size": self.destination_size,
            "source_is_dir": self.source_is_dir,
            "destination_is_dir": self.destination_is_dir,
            "would_overwrite": self.would_overwrite,
            "would_create": self.would_create,
            "would_delete": self.would_delete,
            "risk_level": self.risk_level.value,
            "risk_score": self.risk_score,
            "summary": self.summary,
            "reversible": self.reversible,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


@dataclass
class EmailImpactPreview:
    """Impact preview specific to email operations.

    Shows recipients, subject, whether it would send.
    """
    recipients: List[str] = field(default_factory=list)
    cc: List[str] = field(default_factory=list)
    bcc: List[str] = field(default_factory=list)
    subject: str = ""
    from_email: str = ""
    has_html: bool = False
    has_attachments: bool = False
    attachment_count: int = 0
    would_send: bool = False           # True if SMTP is configured
    invalid_recipients: List[str] = field(default_factory=list)
    risk_level: ImpactRiskLevel = ImpactRiskLevel.NONE
    risk_score: float = 0.0
    summary: str = ""
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "recipients": self.recipients,
            "cc": self.cc,
            "bcc": self.bcc,
            "subject": self.subject,
            "from_email": self.from_email,
            "has_html": self.has_html,
            "has_attachments": self.has_attachments,
            "attachment_count": self.attachment_count,
            "would_send": self.would_send,
            "invalid_recipients": self.invalid_recipients,
            "risk_level": self.risk_level.value,
            "risk_score": self.risk_score,
            "summary": self.summary,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


# ──────────────────────────────────────────────────────────────
#  RETRY HELPER
# ──────────────────────────────────────────────────────────────

def _retry_db_operation(
    func: Any,
    max_retries: int = 3,
    base_delay: float = 0.5,
) -> Any:
    """Execute a function with retry logic for DB operations.

    Args:
        func: Callable to execute.
        max_retries: Maximum number of retries.
        base_delay: Base delay in seconds for exponential backoff.

    Returns:
        The result of the function call.

    Raises:
        The last exception if all retries fail.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "ImpactPreviewEngine: DB retry %d/%d after %.2fs — %s",
                attempt + 1, max_retries, delay, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
        except Exception as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "ImpactPreviewEngine: Unexpected error on retry %d/%d — %s",
                attempt + 1, max_retries, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────
#  IMPACT PREVIEW ENGINE
# ──────────────────────────────────────────────────────────────

class ImpactPreviewEngine:
    """Simulates an action and reports its effects WITHOUT executing it.

    This engine is strictly READ-ONLY — it never modifies data.
    It uses SafetyGate to classify actions for preview routing,
    ensuring the preview respects the same risk taxonomy as
    the execution pipeline.

    Thread-safe: All public methods guarded by RLock.
    """

    def __init__(
        self,
        safety_gate: Optional[SafetyGate] = None,
        db_retry_max: int = 3,
        db_retry_base_delay: float = 0.5,
    ) -> None:
        self._lock = threading.RLock()
        self._safety_gate = safety_gate or get_default_safety_gate()
        self._db_retry_max = db_retry_max
        self._db_retry_base_delay = db_retry_base_delay
        self._preview_count: int = 0

    # ── Public API ────────────────────────────────────────

    def preview_action(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ImpactPreview:
        """Simulate what would happen if the action were executed.

        Routes to the appropriate specialized preview method based on
        action type classification from SafetyGate.

        Args:
            action_type: The type of action to preview (e.g. "database", "file", "email").
            config: The action configuration dict.
            context: Optional context dict.

        Returns:
            An ImpactPreview describing what would happen.
        """
        with self._lock:
            self._preview_count += 1
            context = context or {}

            # Use SafetyGate to classify the action category
            category = self._safety_gate._classify_action(action_type, config)

            # Route to specialized preview based on action type
            action_lower = action_type.lower()

            if action_lower in ("database", "db", "database_operation"):
                db_preview = self.preview_db_operation(config)
                return self._db_preview_to_impact(
                    action_type, category, db_preview,
                )

            if action_lower in ("file", "file_operation"):
                file_preview = self.preview_file_operation(config)
                return self._file_preview_to_impact(
                    action_type, category, file_preview,
                )

            if action_lower in ("email", "send_email"):
                email_preview = self.preview_email(config)
                return self._email_preview_to_impact(
                    action_type, category, email_preview,
                )

            # Generic preview for other action types
            return self._generic_preview(action_type, config, context, category)

    def preview_db_operation(self, config: Dict[str, Any]) -> DBImpactPreview:
        """Preview a database operation WITHOUT executing it.

        For DELETE: counts matching rows using SELECT COUNT(*) with same WHERE.
        For UPDATE: shows before→after diff of field values.
        For INSERT: validates constraints (NOT NULL, UNIQUE, etc.).
        For SELECT: reports row count estimate.

        All operations are strictly READ-ONLY.

        Args:
            config: DB operation config with keys like db_path, operation, query, params.

        Returns:
            A DBImpactPreview with the estimated impact.
        """
        with self._lock:
            db_path = config.get("db_path", ":memory:")
            operation = str(config.get("operation", "query")).upper()
            query = str(config.get("query", ""))
            params = config.get("params", [])
            table = self._extract_table_name(query, operation)

            if not isinstance(params, (list, tuple)):
                params = [params]

            # Base preview
            preview = DBImpactPreview(
                operation=operation,
                table=table,
                risk_level=ImpactRiskLevel.NONE,
                risk_score=0.0,
                summary=f"DB {operation} on table '{table}'",
                reversible=True,
            )

            # Try to connect and inspect
            try:
                if operation in ("DELETE",):
                    preview = self._preview_delete(db_path, query, params, table, preview)
                elif operation in ("UPDATE",):
                    preview = self._preview_update(db_path, query, params, table, preview)
                elif operation in ("INSERT",):
                    preview = self._preview_insert(db_path, query, params, table, preview)
                elif operation in ("QUERY", "SELECT"):
                    preview = self._preview_select(db_path, query, params, table, preview)
                else:
                    preview.summary = f"Unknown DB operation: {operation}"
                    preview.warnings.append(f"Cannot preview unknown operation: {operation}")
            except Exception as exc:
                logger.warning(
                    "ImpactPreviewEngine: DB preview failed for %s on %s: %s",
                    operation, table, exc,
                )
                preview.summary = f"Could not preview DB {operation}: {exc}"
                preview.warnings.append(f"Preview error: {exc}")
                preview.risk_level = ImpactRiskLevel.MEDIUM
                preview.risk_score = 0.4

            return preview

    def preview_file_operation(self, config: Dict[str, Any]) -> FileImpactPreview:
        """Preview a file operation WITHOUT executing it.

        Shows files affected, sizes, whether they exist,
        and whether the operation would overwrite or delete.

        Args:
            config: File operation config with keys like operation, source, destination, base_dir.

        Returns:
            A FileImpactPreview with the estimated impact.
        """
        with self._lock:
            operation = str(config.get("operation", "read")).lower()
            base_dir = config.get("base_dir", os.getcwd())
            source = str(config.get("source", ""))
            destination = str(config.get("destination", ""))

            preview = FileImpactPreview(
                operation=operation,
                source=source,
                destination=destination,
                risk_level=ImpactRiskLevel.NONE,
                risk_score=0.0,
                summary=f"File {operation}",
                reversible=True,
            )

            # Safely resolve paths
            safe_source = self._safe_resolve(source, base_dir)
            safe_dest = self._safe_resolve(destination, base_dir)

            # Inspect source
            if safe_source:
                preview.source_exists = os.path.exists(safe_source)
                if preview.source_exists:
                    try:
                        if os.path.isfile(safe_source):
                            preview.source_size = os.path.getsize(safe_source)
                            preview.source_is_dir = False
                        elif os.path.isdir(safe_source):
                            preview.source_is_dir = True
                            # Count files in directory
                            try:
                                preview.source_size = sum(
                                    os.path.getsize(os.path.join(safe_source, f))
                                    for f in os.listdir(safe_source)
                                    if os.path.isfile(os.path.join(safe_source, f))
                                )
                            except OSError:
                                preview.source_size = 0
                    except OSError:
                        preview.source_size = 0

            # Inspect destination
            if safe_dest:
                preview.destination_exists = os.path.exists(safe_dest)
                if preview.destination_exists:
                    try:
                        if os.path.isfile(safe_dest):
                            preview.destination_size = os.path.getsize(safe_dest)
                            preview.destination_is_dir = False
                        elif os.path.isdir(safe_dest):
                            preview.destination_is_dir = True
                    except OSError:
                        preview.destination_size = 0

            # Compute operation-specific impact
            if operation == "read":
                preview.read_only = True
                preview.reversible = True
                preview.summary = f"Read file: {source}"
                if not preview.source_exists:
                    preview.warnings.append(f"Source file does not exist: {source}")
                    preview.risk_level = ImpactRiskLevel.LOW
                    preview.risk_score = 0.1

            elif operation == "write":
                preview.read_only = False
                preview.would_create = not preview.destination_exists
                preview.would_overwrite = preview.destination_exists
                preview.reversible = False if preview.would_overwrite else True
                preview.summary = (
                    f"Overwrite file: {destination}" if preview.would_overwrite
                    else f"Create file: {destination}"
                )
                if preview.would_overwrite:
                    preview.warnings.append(
                        f"Would overwrite existing file ({preview.destination_size} bytes): {destination}"
                    )
                    preview.risk_level = ImpactRiskLevel.MEDIUM
                    preview.risk_score = 0.4
                else:
                    preview.risk_level = ImpactRiskLevel.LOW
                    preview.risk_score = 0.1

            elif operation == "append":
                preview.read_only = False
                preview.reversible = False
                preview.summary = f"Append to file: {destination or source}"
                if not preview.source_exists and not preview.destination_exists:
                    preview.would_create = True
                    preview.summary = f"Append (creates new file): {destination or source}"
                preview.risk_level = ImpactRiskLevel.LOW
                preview.risk_score = 0.2

            elif operation == "delete":
                preview.read_only = False
                preview.would_delete = preview.source_exists
                preview.reversible = False
                preview.summary = (
                    f"Delete: {source}" if preview.source_exists
                    else f"Delete (not found): {source}"
                )
                if preview.source_exists:
                    size_str = f" ({preview.source_size} bytes)" if not preview.source_is_dir else " (directory)"
                    preview.warnings.append(
                        f"Would permanently delete{size_str}: {source}"
                    )
                    preview.risk_level = ImpactRiskLevel.HIGH
                    preview.risk_score = 0.8
                else:
                    preview.warnings.append(f"Source does not exist: {source}")
                    preview.risk_level = ImpactRiskLevel.LOW
                    preview.risk_score = 0.1

            elif operation == "copy":
                preview.read_only = False
                preview.would_overwrite = preview.destination_exists
                preview.would_create = not preview.destination_exists
                preview.reversible = True
                preview.summary = f"Copy: {source} → {destination}"
                if preview.would_overwrite:
                    preview.warnings.append(
                        f"Would overwrite existing destination: {destination}"
                    )
                    preview.risk_level = ImpactRiskLevel.MEDIUM
                    preview.risk_score = 0.3
                else:
                    preview.risk_level = ImpactRiskLevel.LOW
                    preview.risk_score = 0.1

            elif operation == "move":
                preview.read_only = False
                preview.would_delete = preview.source_exists
                preview.would_overwrite = preview.destination_exists
                preview.would_create = not preview.destination_exists
                preview.reversible = False
                preview.summary = f"Move: {source} → {destination}"
                if preview.destination_exists:
                    preview.warnings.append(
                        f"Would overwrite destination: {destination}"
                    )
                if preview.source_exists:
                    preview.warnings.append(
                        f"Source will be removed after move: {source}"
                    )
                preview.risk_level = ImpactRiskLevel.MEDIUM
                preview.risk_score = 0.5

            else:
                preview.summary = f"File operation: {operation}"
                preview.risk_level = ImpactRiskLevel.LOW
                preview.risk_score = 0.1

            return preview

    def preview_email(self, config: Dict[str, Any]) -> EmailImpactPreview:
        """Preview an email operation WITHOUT sending it.

        Shows recipients, subject, whether it would actually send.

        Args:
            config: Email config with keys like to, subject, body, html, cc, bcc, etc.

        Returns:
            An EmailImpactPreview with the estimated impact.
        """
        with self._lock:
            to_emails = config.get("to", [])
            cc = config.get("cc", [])
            bcc = config.get("bcc", [])
            subject = str(config.get("subject", "No Subject"))
            from_email = str(
                config.get("from_email", "")
                or os.environ.get("SMTP_USER", "noreply@zenic-agents.local")
            )
            html = config.get("html", "")
            attachments = config.get("attachments", [])
            host = config.get("host", os.environ.get("SMTP_HOST", ""))

            # Normalize to lists
            if isinstance(to_emails, str):
                to_emails = [to_emails]
            if isinstance(cc, str):
                cc = [cc]
            if isinstance(bcc, str):
                bcc = [bcc]
            if not isinstance(attachments, list):
                attachments = [attachments] if attachments else []

            # Validate email addresses
            email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
            all_recipients = list(to_emails) + list(cc) + list(bcc)
            invalid = [e for e in all_recipients if not email_pattern.match(str(e))]

            would_send = bool(host) and len(invalid) == 0 and len(to_emails) > 0

            # Determine risk
            subject_lower = subject.lower()
            body_lower = str(config.get("body", "")).lower()
            combined = subject_lower + " " + body_lower
            financial_keywords = (
                "invoice", "factura", "payment", "pago",
                "refund", "reembolso", "charge", "cobro",
            )
            is_financial = any(kw in combined for kw in financial_keywords)

            risk_level = ImpactRiskLevel.LOW
            risk_score = 0.2
            if is_financial:
                risk_level = ImpactRiskLevel.HIGH
                risk_score = 0.7
            elif len(bcc) > 0:
                risk_level = ImpactRiskLevel.MEDIUM
                risk_score = 0.4

            summary_parts: List[str] = []
            if would_send:
                summary_parts.append(f"Would send email to {len(to_emails)} recipient(s)")
            else:
                summary_parts.append("Would NOT send (SMTP not configured or invalid recipients)")
            if cc:
                summary_parts.append(f"{len(cc)} CC")
            if bcc:
                summary_parts.append(f"{len(bcc)} BCC")
            summary = "; ".join(summary_parts)

            warnings: List[str] = []
            if invalid:
                warnings.append(f"Invalid email addresses: {invalid}")
            if not to_emails:
                warnings.append("No recipients specified")
            if is_financial:
                warnings.append("Email contains financial keywords — may require approval")

            preview = EmailImpactPreview(
                recipients=list(to_emails),
                cc=list(cc),
                bcc=list(bcc),
                subject=subject,
                from_email=from_email,
                has_html=bool(html),
                has_attachments=len(attachments) > 0,
                attachment_count=len(attachments),
                would_send=would_send,
                invalid_recipients=invalid,
                risk_level=risk_level,
                risk_score=risk_score,
                summary=summary,
                warnings=warnings,
            )
            return preview

    def compare_scenarios(
        self,
        action_type: str,
        configs: List[Dict[str, Any]],
    ) -> List[ImpactPreview]:
        """A/B comparison of multiple approaches for the same action type.

        Generates an ImpactPreview for each config, allowing the caller
        to compare different approaches before choosing one.

        Args:
            action_type: The type of action to preview.
            configs: List of config dicts, one per scenario.

        Returns:
            A list of ImpactPreview objects, one per config.
        """
        with self._lock:
            results: List[ImpactPreview] = []
            for idx, config in enumerate(configs):
                try:
                    preview = self.preview_action(
                        action_type, config,
                        context={"scenario_index": idx},
                    )
                    preview.metadata["scenario_index"] = idx
                    results.append(preview)
                except Exception as exc:
                    logger.warning(
                        "ImpactPreviewEngine: compare_scenarios failed for config %d: %s",
                        idx, exc,
                    )
                    # Still produce a preview for the failed scenario
                    results.append(ImpactPreview(
                        action_type=action_type,
                        category=ActionCategory.MODERATE,
                        risk_level=ImpactRiskLevel.HIGH,
                        risk_score=0.9,
                        summary=f"Could not preview scenario {idx}: {exc}",
                        warnings=[f"Preview error: {exc}"],
                        metadata={"scenario_index": idx, "error": str(exc)},
                    ))
            return results

    # ── DB Preview Helpers ─────────────────────────────────

    def _preview_delete(
        self,
        db_path: str,
        query: str,
        params: List[Any],
        table: str,
        preview: DBImpactPreview,
    ) -> DBImpactPreview:
        """Preview a DELETE operation: count matching rows using SELECT COUNT(*)."""
        if not table:
            preview.summary = "DELETE without identifiable table"
            preview.risk_level = ImpactRiskLevel.HIGH
            preview.risk_score = 0.9
            preview.warnings.append("Cannot determine target table for DELETE")
            return preview

        # Build COUNT query with same WHERE clause
        where_clause = self._extract_where_clause(query)
        count_query = f"SELECT COUNT(*) FROM {table}"
        if where_clause:
            count_query += f" WHERE {where_clause}"

        def _count_rows() -> int:
            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.execute(count_query, params)
                row = cursor.fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()

        try:
            count = _retry_db_operation(
                _count_rows,
                max_retries=self._db_retry_max,
                base_delay=self._db_retry_base_delay,
            )
            preview.estimated_rows = count
            preview.affected_rows = count
            preview.reversible = False
            preview.summary = f"DELETE from {table}: {count} row(s) would be removed"

            if count == 0:
                preview.risk_level = ImpactRiskLevel.LOW
                preview.risk_score = 0.1
                preview.summary = f"DELETE from {table}: no rows match the WHERE clause"
            elif count > 100:
                preview.risk_level = ImpactRiskLevel.CRITICAL
                preview.risk_score = 1.0
                preview.warnings.append(f"Bulk DELETE: {count} rows would be removed")
            elif count > 10:
                preview.risk_level = ImpactRiskLevel.HIGH
                preview.risk_score = 0.8
                preview.warnings.append(f"Multiple rows affected: {count}")
            else:
                preview.risk_level = ImpactRiskLevel.MEDIUM
                preview.risk_score = 0.5

            # Check if there's no WHERE clause (delete all)
            if not where_clause:
                preview.risk_level = ImpactRiskLevel.CRITICAL
                preview.risk_score = 1.0
                preview.warnings.append("DELETE without WHERE clause — ALL rows would be removed")
                preview.summary = f"DELETE ALL from {table}: {count} row(s) would be removed"

        except Exception as exc:
            preview.summary = f"Could not estimate DELETE impact: {exc}"
            preview.risk_level = ImpactRiskLevel.HIGH
            preview.risk_score = 0.7
            preview.warnings.append(f"Row count estimation failed: {exc}")

        return preview

    def _preview_update(
        self,
        db_path: str,
        query: str,
        params: List[Any],
        table: str,
        preview: DBImpactPreview,
    ) -> DBImpactPreview:
        """Preview an UPDATE operation: show before→after diff of field values."""
        if not table:
            preview.summary = "UPDATE without identifiable table"
            preview.risk_level = ImpactRiskLevel.HIGH
            preview.risk_score = 0.9
            preview.warnings.append("Cannot determine target table for UPDATE")
            return preview

        # Extract SET clause fields
        set_fields = self._extract_set_fields(query)
        where_clause = self._extract_where_clause(query)

        # Count placeholders (?) in the SET clause to correctly slice params.
        # In "UPDATE t SET a = ?, b = ? WHERE c = ?", the first 2 params
        # belong to SET and the rest belong to WHERE.
        set_placeholders = self._count_set_placeholders(query)
        where_params = list(params[set_placeholders:]) if set_placeholders < len(params) else []

        # Count affected rows
        count_query = f"SELECT COUNT(*) FROM {table}"
        if where_clause:
            count_query += f" WHERE {where_clause}"

        def _count_rows() -> int:
            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.execute(count_query, where_params)
                row = cursor.fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()

        try:
            count = _retry_db_operation(
                _count_rows,
                max_retries=self._db_retry_max,
                base_delay=self._db_retry_base_delay,
            )
            preview.estimated_rows = count
            preview.affected_rows = count

            # Fetch a sample row to show current values
            if count > 0:
                sample_query = f"SELECT * FROM {table}"
                if where_clause:
                    sample_query += f" WHERE {where_clause}"
                sample_query += " LIMIT 1"

                def _fetch_sample() -> Optional[Dict[str, Any]]:
                    conn = sqlite3.connect(db_path)
                    conn.row_factory = sqlite3.Row
                    try:
                        cursor = conn.execute(sample_query, where_params)
                        row = cursor.fetchone()
                        return dict(row) if row else None
                    finally:
                        conn.close()

                sample = _retry_db_operation(
                    _fetch_sample,
                    max_retries=self._db_retry_max,
                    base_delay=self._db_retry_base_delay,
                )

                # Build field diffs
                for field_name, proposed_value in set_fields:
                    current_value = None
                    changed = True
                    if sample and field_name in sample:
                        current_value = sample[field_name]
                        changed = (current_value != proposed_value)
                    preview.fields.append(ImpactField(
                        name=field_name,
                        current_value=current_value,
                        proposed_value=proposed_value,
                        field_type=type(proposed_value).__name__ if proposed_value is not None else "unknown",
                        changed=changed,
                    ))

            # Risk assessment
            preview.reversible = False
            field_names = [f.name for f in preview.fields]
            preview.summary = (
                f"UPDATE {table}: {count} row(s), fields: {', '.join(field_names) if field_names else 'unknown'}"
            )

            if not where_clause:
                preview.risk_level = ImpactRiskLevel.CRITICAL
                preview.risk_score = 1.0
                preview.warnings.append("UPDATE without WHERE clause — ALL rows would be affected")
            elif count > 100:
                preview.risk_level = ImpactRiskLevel.HIGH
                preview.risk_score = 0.8
                preview.warnings.append(f"Bulk UPDATE: {count} rows affected")
            elif count > 10:
                preview.risk_level = ImpactRiskLevel.MEDIUM
                preview.risk_score = 0.5
            else:
                preview.risk_level = ImpactRiskLevel.LOW
                preview.risk_score = 0.3

        except Exception as exc:
            preview.summary = f"Could not estimate UPDATE impact: {exc}"
            preview.risk_level = ImpactRiskLevel.HIGH
            preview.risk_score = 0.7
            preview.warnings.append(f"Impact estimation failed: {exc}")

        return preview

    def _preview_insert(
        self,
        db_path: str,
        query: str,
        params: List[Any],
        table: str,
        preview: DBImpactPreview,
    ) -> DBImpactPreview:
        """Preview an INSERT operation: validate constraints."""
        if not table:
            preview.summary = "INSERT without identifiable table"
            preview.risk_level = ImpactRiskLevel.HIGH
            preview.risk_score = 0.9
            preview.warnings.append("Cannot determine target table for INSERT")
            return preview

        # Inspect table schema to validate constraints
        def _inspect_schema() -> List[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(f"PRAGMA table_info({table})")
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

        try:
            columns = _retry_db_operation(
                _inspect_schema,
                max_retries=self._db_retry_max,
                base_delay=self._db_retry_base_delay,
            )

            if not columns:
                preview.warnings.append(f"Table '{table}' not found or has no columns")
                preview.constraints_valid = False
                preview.constraint_violations.append(f"Table '{table}' does not exist")
                preview.risk_level = ImpactRiskLevel.HIGH
                preview.risk_score = 0.8
                preview.summary = f"INSERT into {table}: table does not exist"
                return preview

            # Check NOT NULL constraints
            for col in columns:
                col_name = col.get("name", "")
                notnull = col.get("notnull", 0)
                if notnull:
                    # Check if a corresponding param exists
                    col_idx = None
                    # Try to find column index from query
                    insert_cols = self._extract_insert_columns(query)
                    if insert_cols:
                        try:
                            col_idx = insert_cols.index(col_name)
                        except ValueError:
                            pass

                    if col_idx is not None and col_idx < len(params):
                        if params[col_idx] is None:
                            preview.constraints_valid = False
                            preview.constraint_violations.append(
                                f"NOT NULL violation: column '{col_name}' cannot be NULL"
                            )
                    elif col_idx is None and not query.upper().startswith("INSERT INTO"):
                        # Fallback: if we can't parse, warn
                        pass

            # Check UNIQUE constraints
            def _get_unique_constraints() -> List[List[str]]:
                conn = sqlite3.connect(db_path)
                try:
                    cursor = conn.execute(f"PRAGMA index_list({table})")
                    indexes = cursor.fetchall()
                    unique_constraints: List[List[str]] = []
                    for idx_row in indexes:
                        if idx_row[2]:  # unique flag
                            idx_name = idx_row[1]
                            col_cursor = conn.execute(f"PRAGMA index_info({idx_name})")
                            cols = [row[2] for row in col_cursor.fetchall()]
                            unique_constraints.append(cols)
                    return unique_constraints
                finally:
                    conn.close()

            unique_groups = _retry_db_operation(
                _get_unique_constraints,
                max_retries=self._db_retry_max,
                base_delay=self._db_retry_base_delay,
            )

            for unique_cols in unique_groups:
                insert_cols = self._extract_insert_columns(query)
                if insert_cols:
                    matching_indices = []
                    all_present = True
                    for uc in unique_cols:
                        try:
                            matching_indices.append(insert_cols.index(uc))
                        except ValueError:
                            all_present = False
                            break

                    if all_present and matching_indices:
                        # Check for existing rows with same unique values
                        where_parts = [f"{unique_cols[i]} = ?" for i in range(len(unique_cols))]
                        check_query = f"SELECT COUNT(*) FROM {table} WHERE {' AND '.join(where_parts)}"
                        check_params = [params[i] for i in matching_indices if i < len(params)]

                        def _check_unique() -> int:
                            conn = sqlite3.connect(db_path)
                            try:
                                cursor = conn.execute(check_query, check_params)
                                row = cursor.fetchone()
                                return int(row[0]) if row else 0
                            finally:
                                conn.close()

                        existing = _retry_db_operation(
                            _check_unique,
                            max_retries=self._db_retry_max,
                            base_delay=self._db_retry_base_delay,
                        )
                        if existing > 0:
                            preview.constraints_valid = False
                            preview.constraint_violations.append(
                                f"UNIQUE violation: ({', '.join(unique_cols)}) already exists"
                            )

            preview.affected_rows = 1
            preview.estimated_rows = 1
            preview.reversible = True  # DELETE can undo INSERT
            insert_cols = self._extract_insert_columns(query)
            preview.summary = (
                f"INSERT into {table}: 1 row, columns: {', '.join(insert_cols) if insert_cols else 'unknown'}"
            )

            if preview.constraints_valid:
                preview.risk_level = ImpactRiskLevel.LOW
                preview.risk_score = 0.2
            else:
                preview.risk_level = ImpactRiskLevel.MEDIUM
                preview.risk_score = 0.5
                preview.summary += " (constraint violations detected)"

        except Exception as exc:
            preview.summary = f"Could not estimate INSERT impact: {exc}"
            preview.risk_level = ImpactRiskLevel.HIGH
            preview.risk_score = 0.7
            preview.warnings.append(f"Constraint check failed: {exc}")

        return preview

    def _preview_select(
        self,
        db_path: str,
        query: str,
        params: List[Any],
        table: str,
        preview: DBImpactPreview,
    ) -> DBImpactPreview:
        """Preview a SELECT/QUERY operation: report row count estimate."""
        # SELECT is read-only, low risk
        preview.reversible = True
        preview.read_only = True

        # Try to estimate row count
        if table:
            count_query = f"SELECT COUNT(*) FROM {table}"
            where_clause = self._extract_where_clause(query)
            if where_clause:
                count_query += f" WHERE {where_clause}"

            def _count_rows() -> int:
                conn = sqlite3.connect(db_path)
                try:
                    cursor = conn.execute(count_query, params)
                    row = cursor.fetchone()
                    return int(row[0]) if row else 0
                finally:
                    conn.close()

            try:
                count = _retry_db_operation(
                    _count_rows,
                    max_retries=self._db_retry_max,
                    base_delay=self._db_retry_base_delay,
                )
                preview.estimated_rows = count
                preview.summary = f"SELECT from {table}: ~{count} row(s) would be returned"
            except Exception as exc:
                preview.summary = f"SELECT from {table}: could not estimate row count"
                preview.warnings.append(f"Row count estimation failed: {exc}")
        else:
            preview.summary = "SELECT query: read-only operation"

        preview.risk_level = ImpactRiskLevel.NONE
        preview.risk_score = 0.0
        return preview

    # ── SQL Parsing Helpers ────────────────────────────────

    @staticmethod
    def _extract_table_name(query: str, operation: str) -> str:
        """Extract the table name from a SQL query.

        Handles:
          - DELETE FROM table ...
          - UPDATE table SET ...
          - INSERT INTO table ...
          - SELECT ... FROM table ...
        """
        query_upper = query.upper().strip()

        if operation in ("DELETE",):
            match = re.search(r'\bFROM\s+(\w+)', query_upper)
            return match.group(1).lower() if match else ""

        if operation in ("UPDATE",):
            match = re.search(r'\bUPDATE\s+(\w+)', query_upper)
            return match.group(1).lower() if match else ""

        if operation in ("INSERT",):
            match = re.search(r'\bINTO\s+(\w+)', query_upper)
            return match.group(1).lower() if match else ""

        if operation in ("QUERY", "SELECT"):
            match = re.search(r'\bFROM\s+(\w+)', query_upper)
            return match.group(1).lower() if match else ""

        return ""

    @staticmethod
    def _extract_where_clause(query: str) -> str:
        """Extract the WHERE clause from a SQL query (without the WHERE keyword)."""
        match = re.search(
            r'\bWHERE\s+(.*?)(?:\s*;\s*$|\s*$|\s+GROUP\s+|\s+ORDER\s+|\s+LIMIT\s+)',
            query,
            re.IGNORECASE | re.DOTALL,
        )
        if match:
            return match.group(1).strip()
        # Fallback: everything after WHERE to end
        match = re.search(r'\bWHERE\s+(.*)', query, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip().rstrip(";").strip() if match else ""

    @staticmethod
    def _extract_set_fields(query: str) -> List[tuple]:
        """Extract field=value pairs from UPDATE SET clause.

        Returns list of (field_name, value) tuples.
        Note: values from the query string are symbolic; actual values come from params.
        """
        match = re.search(r'\bSET\s+(.*?)\s+WHERE\b', query, re.IGNORECASE | re.DOTALL)
        if not match:
            # No WHERE clause — SET to end
            match = re.search(r'\bSET\s+(.*)', query, re.IGNORECASE | re.DOTALL)

        if not match:
            return []

        set_clause = match.group(1).strip().rstrip(";")
        fields: List[tuple] = []

        for assignment in set_clause.split(","):
            assignment = assignment.strip()
            eq_match = re.match(r'(\w+)\s*=\s*(.+)', assignment)
            if eq_match:
                field_name = eq_match.group(1)
                value_str = eq_match.group(2).strip()
                # If value is a placeholder (?), mark it as parameterized
                if value_str == "?":
                    fields.append((field_name, "<parameterized>"))
                else:
                    # Try to parse as a value
                    try:
                        if value_str.startswith("'") and value_str.endswith("'"):
                            fields.append((field_name, value_str[1:-1]))
                        elif value_str.upper() == "NULL":
                            fields.append((field_name, None))
                        else:
                            fields.append((field_name, value_str))
                    except Exception:
                        fields.append((field_name, value_str))

        return fields

    @staticmethod
    def _extract_insert_columns(query: str) -> List[str]:
        """Extract column names from an INSERT INTO table (col1, col2, ...) statement."""
        match = re.search(
            r'\bINTO\s+\w+\s*\(([^)]+)\)',
            query,
            re.IGNORECASE,
        )
        if not match:
            return []
        cols_str = match.group(1)
        return [c.strip() for c in cols_str.split(",")]

    @staticmethod
    def _count_set_placeholders(query: str) -> int:
        """Count the number of '?' placeholders in the SET clause of an UPDATE.

        This allows proper slicing of the params list so that only the
        WHERE-related params are passed to the COUNT / sample queries.

        Example:
          "UPDATE t SET a = ?, b = ? WHERE c = ?"  →  2
          "UPDATE t SET a = 5 WHERE c = ?"          →  0
        """
        # Extract the SET clause (between SET and WHERE, or SET to end)
        match = re.search(r'\bSET\s+(.*?)\s+WHERE\b', query, re.IGNORECASE | re.DOTALL)
        if not match:
            match = re.search(r'\bSET\s+(.*)', query, re.IGNORECASE | re.DOTALL)
        if not match:
            return 0
        set_clause = match.group(1)
        return set_clause.count('?')

    # ── Path Resolution Helper ─────────────────────────────

    @staticmethod
    def _safe_resolve(path: str, base_dir: str) -> Optional[str]:
        """Safely resolve a file path within base_dir.

        Returns None if path is empty or would escape base_dir.
        """
        if not path:
            return None
        try:
            base = os.path.realpath(base_dir) if base_dir else os.path.realpath(os.getcwd())
            if os.path.isabs(path):
                resolved = os.path.realpath(path)
                if resolved.startswith(base + os.sep) or resolved == base:
                    return resolved
                return None  # Path traversal
            resolved = os.path.realpath(os.path.join(base, path))
            if resolved.startswith(base + os.sep) or resolved == base:
                return resolved
            return None  # Path traversal
        except Exception:
            return None

    # ── Conversion Helpers ─────────────────────────────────

    def _db_preview_to_impact(
        self,
        action_type: str,
        category: ActionCategory,
        db_preview: DBImpactPreview,
    ) -> ImpactPreview:
        """Convert a DBImpactPreview to a generic ImpactPreview."""
        return ImpactPreview(
            action_type=action_type,
            category=category,
            risk_level=db_preview.risk_level,
            risk_score=db_preview.risk_score,
            summary=db_preview.summary,
            affected_resources=[db_preview.table] if db_preview.table else [],
            fields=db_preview.fields,
            warnings=db_preview.warnings,
            reversible=db_preview.reversible,
            read_only=db_preview.operation in ("QUERY", "SELECT"),
            metadata={
                "preview_type": "database",
                "operation": db_preview.operation,
                "estimated_rows": db_preview.estimated_rows,
                "affected_rows": db_preview.affected_rows,
                "constraints_valid": db_preview.constraints_valid,
                **db_preview.metadata,
            },
        )

    def _file_preview_to_impact(
        self,
        action_type: str,
        category: ActionCategory,
        file_preview: FileImpactPreview,
    ) -> ImpactPreview:
        """Convert a FileImpactPreview to a generic ImpactPreview."""
        resources: List[str] = []
        if file_preview.source:
            resources.append(file_preview.source)
        if file_preview.destination and file_preview.destination != file_preview.source:
            resources.append(file_preview.destination)

        return ImpactPreview(
            action_type=action_type,
            category=category,
            risk_level=file_preview.risk_level,
            risk_score=file_preview.risk_score,
            summary=file_preview.summary,
            affected_resources=resources,
            warnings=file_preview.warnings,
            reversible=file_preview.reversible,
            read_only=file_preview.operation == "read",
            metadata={
                "preview_type": "file",
                "operation": file_preview.operation,
                "source_exists": file_preview.source_exists,
                "destination_exists": file_preview.destination_exists,
                "would_overwrite": file_preview.would_overwrite,
                "would_create": file_preview.would_create,
                "would_delete": file_preview.would_delete,
                **file_preview.metadata,
            },
        )

    def _email_preview_to_impact(
        self,
        action_type: str,
        category: ActionCategory,
        email_preview: EmailImpactPreview,
    ) -> ImpactPreview:
        """Convert an EmailImpactPreview to a generic ImpactPreview."""
        return ImpactPreview(
            action_type=action_type,
            category=category,
            risk_level=email_preview.risk_level,
            risk_score=email_preview.risk_score,
            summary=email_preview.summary,
            affected_resources=email_preview.recipients,
            warnings=email_preview.warnings,
            reversible=False,  # Emails cannot be un-sent
            read_only=False,
            metadata={
                "preview_type": "email",
                "would_send": email_preview.would_send,
                "recipient_count": len(email_preview.recipients),
                "has_attachments": email_preview.has_attachments,
                **email_preview.metadata,
            },
        )

    def _generic_preview(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Dict[str, Any],
        category: ActionCategory,
    ) -> ImpactPreview:
        """Generate a generic preview for action types without specialized handlers."""
        # Determine risk from category
        risk_map: Dict[ActionCategory, tuple] = {
            ActionCategory.SAFE: (ImpactRiskLevel.NONE, 0.0),
            ActionCategory.MODERATE: (ImpactRiskLevel.LOW, 0.2),
            ActionCategory.DESTRUCTIVE: (ImpactRiskLevel.HIGH, 0.8),
            ActionCategory.FINANCIAL: (ImpactRiskLevel.HIGH, 0.7),
            ActionCategory.SYSTEM: (ImpactRiskLevel.MEDIUM, 0.6),
        }
        risk_level, risk_score = risk_map.get(category, (ImpactRiskLevel.MEDIUM, 0.5))

        # Build affected resources from config keys
        affected: List[str] = []
        for key in ("url", "endpoint", "webhook_url", "channel", "target"):
            val = config.get(key)
            if val:
                affected.append(str(val))

        # Build fields from config
        fields: List[ImpactField] = []
        for key, value in config.items():
            if isinstance(value, (str, int, float, bool)):
                fields.append(ImpactField(
                    name=key,
                    proposed_value=value,
                    field_type=type(value).__name__,
                ))

        return ImpactPreview(
            action_type=action_type,
            category=category,
            risk_level=risk_level,
            risk_score=risk_score,
            summary=f"Action '{action_type}' classified as {category.value}",
            affected_resources=affected,
            fields=fields,
            reversible=category in (ActionCategory.SAFE, ActionCategory.MODERATE),
            read_only=category == ActionCategory.SAFE,
            metadata={
                "preview_type": "generic",
                "context_keys": list(context.keys()) if context else [],
            },
        )

    # ── Stats ──────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        with self._lock:
            return {
                "preview_count": self._preview_count,
            }


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_impact_preview_engine: Optional[ImpactPreviewEngine] = None
_impact_preview_lock = threading.Lock()


def get_impact_preview_engine() -> ImpactPreviewEngine:
    """Get or create the global ImpactPreviewEngine instance."""
    global _impact_preview_engine
    with _impact_preview_lock:
        if _impact_preview_engine is None:
            _impact_preview_engine = ImpactPreviewEngine()
        return _impact_preview_engine


def reset_impact_preview_engine() -> None:
    """Reset the global ImpactPreviewEngine (for testing)."""
    global _impact_preview_engine
    with _impact_preview_lock:
        _impact_preview_engine = None


__all__ = [
    # Dataclasses
    "ImpactField",
    "ImpactPreview",
    "DBImpactPreview",
    "FileImpactPreview",
    "EmailImpactPreview",
    # Enums
    "ImpactRiskLevel",
    # Engine
    "ImpactPreviewEngine",
    # Singleton
    "get_impact_preview_engine",
    "reset_impact_preview_engine",
]
