"""
ZENIC-AGENTS - Diff Preview Engine (C1: Simulation Engine)

Shows before/after diffs of what changes would occur if an action
were executed.  For each action type the engine inspects the current
state and computes the delta:

* **DB**   – uses DBTransactionJournal to get current snapshots,
  then computes what would change.
* **File** – compares current file state with proposed changes.
* **Email** – shows the email that would be sent (from, to, subject).

Thread-safe: All public methods guarded by RLock.
Retry logic: DB reads wrapped with 3 retries, exponential backoff.
Singleton: get_diff_preview_engine() / reset_diff_preview_engine().
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "DiffEntry",
    "DiffResult",
    "DiffPreviewEngine",
    "get_diff_preview_engine",
    "reset_diff_preview_engine",
]


# ──────────────────────────────────────────────────────────────
#  DATA MODELS
# ──────────────────────────────────────────────────────────────

@dataclass
class DiffEntry:
    """A single field-level diff between the current and proposed state.

    Attributes:
        field_path: Dot-separated path to the field (e.g.
            ``"users.name"``, ``"config.timeout"``).
        old_value: The current value of the field (``None`` if
            the field does not exist yet).
        new_value: The proposed value (``None`` if the field
            would be removed).
        change_type: One of ``"added"``, ``"modified"``, or
            ``"removed"``.
    """

    field_path: str
    old_value: Any = None
    new_value: Any = None
    change_type: str = "modified"  # "added" | "modified" | "removed"

    def __post_init__(self) -> None:
        # Validate change_type
        if self.change_type not in ("added", "modified", "removed"):
            self.change_type = "modified"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "field_path": self.field_path,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "change_type": self.change_type,
        }


@dataclass
class DiffResult:
    """Result of a diff preview for a single action.

    Attributes:
        action_type: The type of action that was diffed.
        diffs: List of field-level diffs.
        affected_tables: List of database tables that would be
            affected (empty for non-DB actions).
        affected_files: List of file paths that would be affected
            (empty for non-file actions).
        estimated_risk: Overall risk assessment: ``"low"``,
            ``"medium"``, or ``"high"``.
        summary: Human-readable summary of the diff.
    """

    action_type: str
    diffs: List[DiffEntry] = field(default_factory=list)
    affected_tables: List[str] = field(default_factory=list)
    affected_files: List[str] = field(default_factory=list)
    estimated_risk: str = "low"  # "low" | "medium" | "high"
    summary: str = ""

    def __post_init__(self) -> None:
        if self.estimated_risk not in ("low", "medium", "high"):
            self.estimated_risk = "low"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "action_type": self.action_type,
            "diffs": [d.to_dict() for d in self.diffs],
            "affected_tables": self.affected_tables,
            "affected_files": self.affected_files,
            "estimated_risk": self.estimated_risk,
            "summary": self.summary,
        }


# ──────────────────────────────────────────────────────────────
#  RETRY HELPER
# ──────────────────────────────────────────────────────────────

def _retry(
    fn: Any,
    max_retries: int = 3,
    base_delay: float = 0.1,
    label: str = "diff_preview",
) -> Any:
    """Execute *fn* with exponential-backoff retry.

    Delays: base_delay * 2^attempt  →  0.1s, 0.2s, 0.4s.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.debug(
                    "%s: retry %d/%d after %.2fs — %s",
                    label, attempt + 1, max_retries, delay, exc,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "%s: failed after %d attempts — %s",
                    label, max_retries, exc,
                )
    raise last_exc  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────
#  DIFF PREVIEW ENGINE
# ──────────────────────────────────────────────────────────────

class DiffPreviewEngine:
    """Shows before/after diffs of what changes would occur if an
    action were executed.

    For each action type the engine inspects the current state and
    computes the delta:

    * **DB operations** – uses DBTransactionJournal to get current
      snapshots, then computes what would change.
    * **File operations** – compares current file state with proposed
      changes.
    * **Email operations** – shows the email that would be sent.

    Thread-safe: All public methods guarded by RLock.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._db_journal: Optional[Any] = None  # lazy
        self._preview_count: int = 0

    # ── Lazy dependencies ──────────────────────────────────────

    @property
    def db_journal(self) -> Any:
        """Lazy-load the DBTransactionJournal singleton."""
        if self._db_journal is None:
            from .db_journal import DBTransactionJournal, get_db_journal
            self._db_journal = get_db_journal()
        return self._db_journal

    # ── Core API ───────────────────────────────────────────────

    def preview_diff(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> DiffResult:
        """Compute a before/after diff for the given action.

        Routes to the appropriate specialised diff method based on
        the action type.

        Args:
            action_type: The type of action (e.g. ``"database"``,
                ``"file"``, ``"email"``).
            config: The action configuration dict.
            context: Optional context dict.

        Returns:
            A DiffResult describing all changes the action would make.
        """
        with self._lock:
            self._preview_count += 1
            context = context or {}

            action_lower = action_type.lower()

            if action_lower in ("database", "db", "database_operation"):
                return self._diff_db(config, context)
            elif action_lower in ("file", "file_operation"):
                return self._diff_file(config, context)
            elif action_lower in ("email", "send_email"):
                return self._diff_email(config, context)
            else:
                return self._diff_generic(action_type, config, context)

    # ── DB diff ────────────────────────────────────────────────

    def _diff_db(
        self,
        config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> DiffResult:
        """Compute a diff for a database operation.

        Uses DBTransactionJournal to get the current snapshot, then
        computes what would change.

        Args:
            config: DB operation config with keys like db_path,
                operation, query, params, table.
            context: Optional context dict.

        Returns:
            A DiffResult with DB-specific diffs.
        """
        diffs: List[DiffEntry] = []
        affected_tables: List[str] = []

        db_path = config.get("db_path", ":memory:")
        operation = str(config.get("operation", "query")).upper()
        query = config.get("query", "")
        table = config.get("table", "")
        params = config.get("params", [])

        if not isinstance(params, (list, tuple)):
            params = [params] if params else []

        if table:
            affected_tables.append(table)

        # ── Get current snapshot via journal ──────────────────
        current_rows: List[Dict[str, Any]] = []
        if table and db_path != ":memory:" and operation in ("DELETE", "UPDATE"):
            try:
                current_rows = self._fetch_current_rows(
                    db_path, operation, query, list(params), table,
                )
            except Exception as exc:
                logger.debug(
                    "DiffPreviewEngine: could not fetch current rows for %s: %s",
                    operation, exc,
                )

        # ── Compute diffs based on operation ──────────────────
        if operation == "DELETE":
            for row_idx, row in enumerate(current_rows):
                for col_name, col_value in row.items():
                    diffs.append(DiffEntry(
                        field_path=f"{table}.{col_name}[row{row_idx}]",
                        old_value=col_value,
                        new_value=None,
                        change_type="removed",
                    ))

        elif operation == "UPDATE":
            # Parse SET clause to find proposed values
            set_fields = self._parse_set_fields(query)
            set_placeholders = self._count_placeholders_in_set(query)
            where_params = list(params[set_placeholders:]) if set_placeholders < len(params) else []

            if current_rows and set_fields:
                for row_idx, row in enumerate(current_rows[:1]):  # sample first row
                    for field_name, proposed_value in set_fields:
                        current_value = row.get(field_name)
                        changed = current_value != proposed_value
                        change_type = "modified" if current_value is not None else "added"
                        diffs.append(DiffEntry(
                            field_path=f"{table}.{field_name}[row{row_idx}]",
                            old_value=current_value,
                            new_value=proposed_value,
                            change_type=change_type if changed else "modified",
                        ))

        elif operation == "INSERT":
            # INSERT adds new data — all fields are "added"
            insert_cols = self._parse_insert_columns(query)
            for idx, col_name in enumerate(insert_cols):
                value = params[idx] if idx < len(params) else None
                diffs.append(DiffEntry(
                    field_path=f"{table}.{col_name}",
                    old_value=None,
                    new_value=value,
                    change_type="added",
                ))

        # Compute risk and summary
        risk = self.estimate_risk_from_diffs(diffs, operation)
        summary = self._build_db_summary(operation, table, len(current_rows), diffs)

        return DiffResult(
            action_type="database",
            diffs=diffs,
            affected_tables=affected_tables,
            affected_files=[],
            estimated_risk=risk,
            summary=summary,
        )

    def _fetch_current_rows(
        self,
        db_path: str,
        operation: str,
        query: str,
        params: List[Any],
        table: str,
    ) -> List[Dict[str, Any]]:
        """Fetch current rows that would be affected by the operation.

        Wrapped in retry logic for DB read resilience.
        """
        def _do_fetch() -> List[Dict[str, Any]]:
            if db_path == ":memory:":
                return []

            # Build a SELECT query
            where_clause = self._extract_where_clause(query, operation)
            select_query = f"SELECT * FROM {table}"
            select_params: List[Any] = []

            if where_clause:
                select_query += f" WHERE {where_clause}"
                if operation == "UPDATE":
                    set_placeholders = self._count_placeholders_in_set(query)
                    select_params = list(params[set_placeholders:])
                else:
                    select_params = list(params)

            select_query += " LIMIT 100"  # safety limit

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(select_query, select_params)
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

        return _retry(
            _do_fetch,
            max_retries=3,
            base_delay=0.1,
            label=f"DiffPreviewEngine._fetch_current_rows({table})",
        )

    # ── File diff ──────────────────────────────────────────────

    def _diff_file(
        self,
        config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> DiffResult:
        """Compute a diff for a file operation.

        Compares current file state with proposed changes.

        Args:
            config: File operation config with keys like operation,
                source, destination, content, base_dir.
            context: Optional context dict.

        Returns:
            A DiffResult with file-specific diffs.
        """
        diffs: List[DiffEntry] = []
        affected_files: List[str] = []

        operation = str(config.get("operation", "read")).lower()
        source = str(config.get("source", ""))
        destination = str(config.get("destination", ""))
        content = config.get("content")
        base_dir = config.get("base_dir", os.getcwd())

        target_path = destination or source
        if target_path:
            affected_files.append(target_path)

        if operation == "write":
            # File would be created or overwritten
            exists = os.path.exists(os.path.join(base_dir, target_path)) if target_path else False
            if exists:
                diffs.append(DiffEntry(
                    field_path=target_path,
                    old_value="<existing_file>",
                    new_value=content if content is not None else "<new_content>",
                    change_type="modified",
                ))
            else:
                diffs.append(DiffEntry(
                    field_path=target_path,
                    old_value=None,
                    new_value=content if content is not None else "<new_content>",
                    change_type="added",
                ))

        elif operation == "delete":
            exists = os.path.exists(os.path.join(base_dir, source)) if source else False
            if exists:
                diffs.append(DiffEntry(
                    field_path=source,
                    old_value="<existing_file>",
                    new_value=None,
                    change_type="removed",
                ))

        elif operation == "append":
            diffs.append(DiffEntry(
                field_path=target_path,
                old_value="<current_content>",
                new_value="<current_content + appended_data>",
                change_type="modified",
            ))

        elif operation == "move":
            if source:
                diffs.append(DiffEntry(
                    field_path=source,
                    old_value="<existing_file>",
                    new_value=None,
                    change_type="removed",
                ))
            if destination:
                dest_exists = os.path.exists(os.path.join(base_dir, destination)) if destination else False
                diffs.append(DiffEntry(
                    field_path=destination,
                    old_value="<existing_file>" if dest_exists else None,
                    new_value="<moved_file>",
                    change_type="modified" if dest_exists else "added",
                ))

        elif operation == "copy":
            if destination:
                dest_exists = os.path.exists(os.path.join(base_dir, destination)) if destination else False
                diffs.append(DiffEntry(
                    field_path=destination,
                    old_value="<existing_file>" if dest_exists else None,
                    new_value="<copied_file>",
                    change_type="modified" if dest_exists else "added",
                ))

        else:
            # read or unknown — no changes
            diffs.append(DiffEntry(
                field_path=target_path,
                old_value="<current>",
                new_value="<current>",
                change_type="modified",
            ))

        risk = self.estimate_risk_from_diffs(diffs, operation)
        summary = f"File {operation}: {target_path}" if target_path else f"File {operation}"

        return DiffResult(
            action_type="file",
            diffs=diffs,
            affected_tables=[],
            affected_files=affected_files,
            estimated_risk=risk,
            summary=summary,
        )

    # ── Email diff ─────────────────────────────────────────────

    def _diff_email(
        self,
        config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> DiffResult:
        """Compute a diff for an email operation.

        Shows the email that would be sent (from, to, subject).

        Args:
            config: Email config with keys like to, subject, body,
                from_email, cc, bcc.
            context: Optional context dict.

        Returns:
            A DiffResult with email-specific diffs.
        """
        diffs: List[DiffEntry] = []

        to_emails = config.get("to", [])
        if isinstance(to_emails, str):
            to_emails = [to_emails]
        subject = config.get("subject", "")
        from_email = config.get("from_email", "")
        cc = config.get("cc", [])
        bcc = config.get("bcc", [])

        diffs.append(DiffEntry(
            field_path="email.from",
            old_value=None,
            new_value=from_email,
            change_type="added",
        ))
        diffs.append(DiffEntry(
            field_path="email.to",
            old_value=None,
            new_value=[str(r) for r in to_emails],
            change_type="added",
        ))
        diffs.append(DiffEntry(
            field_path="email.subject",
            old_value=None,
            new_value=subject,
            change_type="added",
        ))
        if cc:
            diffs.append(DiffEntry(
                field_path="email.cc",
                old_value=None,
                new_value=[str(c) for c in cc] if isinstance(cc, list) else [str(cc)],
                change_type="added",
            ))
        if bcc:
            diffs.append(DiffEntry(
                field_path="email.bcc",
                old_value=None,
                new_value=[str(b) for b in bcc] if isinstance(bcc, list) else [str(bcc)],
                change_type="added",
            ))

        risk = self.estimate_risk_from_diffs(diffs, "send_email")
        summary = (
            f"Would send email from '{from_email}' to "
            f"{len(to_emails)} recipient(s) with subject '{subject}'"
        )

        return DiffResult(
            action_type="email",
            diffs=diffs,
            affected_tables=[],
            affected_files=[],
            estimated_risk=risk,
            summary=summary,
        )

    # ── Generic diff ───────────────────────────────────────────

    def _diff_generic(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> DiffResult:
        """Compute a generic diff for any action type.

        Compares config keys as potential changes.

        Args:
            action_type: The action type string.
            config: The action configuration dict.
            context: Optional context dict.

        Returns:
            A DiffResult with generic diffs.
        """
        diffs: List[DiffEntry] = []

        for key, value in config.items():
            diffs.append(DiffEntry(
                field_path=f"{action_type}.{key}",
                old_value=None,
                new_value=value,
                change_type="added",
            ))

        risk = self.estimate_risk_from_diffs(diffs, action_type)
        summary = f"Generic diff for {action_type}: {len(diffs)} field(s) would change"

        return DiffResult(
            action_type=action_type,
            diffs=diffs,
            affected_tables=[],
            affected_files=[],
            estimated_risk=risk,
            summary=summary,
        )

    # ── Formatting ─────────────────────────────────────────────

    def format_diff(
        self,
        diff_result: DiffResult,
        format: str = "text",
    ) -> str:
        """Format a DiffResult as text or JSON.

        Args:
            diff_result: The diff result to format.
            format: Output format — ``"text"`` (default) or ``"json"``.

        Returns:
            Formatted string representation.
        """
        with self._lock:
            if format.lower() == "json":
                return json.dumps(diff_result.to_dict(), indent=2, default=str)

            # Text format
            lines: List[str] = []
            lines.append(f"Diff Preview: {diff_result.action_type}")
            lines.append(f"Risk: {diff_result.estimated_risk}")
            lines.append(f"Summary: {diff_result.summary}")
            lines.append("")

            if diff_result.affected_tables:
                lines.append(f"Affected tables: {', '.join(diff_result.affected_tables)}")
            if diff_result.affected_files:
                lines.append(f"Affected files: {', '.join(diff_result.affected_files)}")

            if diff_result.diffs:
                lines.append("")
                lines.append("Changes:")
                for d in diff_result.diffs:
                    change_symbol = {
                        "added": "+",
                        "modified": "~",
                        "removed": "-",
                    }.get(d.change_type, "?")
                    lines.append(
                        f"  [{change_symbol}] {d.field_path}: "
                        f"{_truncate(d.old_value)} → {_truncate(d.new_value)}"
                    )

            return "\n".join(lines)

    # ── Risk estimation ────────────────────────────────────────

    def estimate_risk(
        self,
        diff_result: DiffResult,
    ) -> str:
        """Estimate risk level based on the number and type of diffs.

        Counts modified/removed fields and assesses risk:

        * **high**   – 5+ removed fields, or 10+ total changes.
        * **medium** – 2+ removed fields, or 5+ total changes.
        * **low**    – otherwise.

        Args:
            diff_result: The diff result to assess.

        Returns:
            One of ``"low"``, ``"medium"``, ``"high"``.
        """
        with self._lock:
            return self.estimate_risk_from_diffs(
                diff_result.diffs, diff_result.action_type,
            )

    @staticmethod
    def estimate_risk_from_diffs(
        diffs: List[DiffEntry],
        operation: str = "",
    ) -> str:
        """Estimate risk from a list of DiffEntry objects.

        Args:
            diffs: The list of diffs.
            operation: Optional operation name for context.

        Returns:
            One of ``"low"``, ``"medium"``, ``"high"``.
        """
        removed_count = sum(1 for d in diffs if d.change_type == "removed")
        modified_count = sum(1 for d in diffs if d.change_type == "modified")
        total_count = len(diffs)

        # High-risk indicators
        if removed_count >= 5 or total_count >= 10:
            return "high"

        # DELETE operations are inherently riskier
        op_upper = operation.upper() if isinstance(operation, str) else ""
        if op_upper == "DELETE" and removed_count > 0:
            return "high"

        # Medium-risk indicators
        if removed_count >= 2 or total_count >= 5 or modified_count >= 3:
            return "medium"

        return "low"

    # ── SQL parsing helpers ────────────────────────────────────

    @staticmethod
    def _extract_where_clause(query: str, operation: str) -> str:
        """Best-effort extraction of WHERE clause from a SQL query."""
        import re
        op_upper = operation.upper()

        if op_upper == "DELETE":
            m = re.match(
                r"^\s*DELETE\s+FROM\s+\w+\s+WHERE\s+(.+)$",
                query, re.IGNORECASE | re.DOTALL,
            )
            return m.group(1).strip() if m else ""

        if op_upper == "UPDATE":
            m = re.match(
                r"^\s*UPDATE\s+\w+\s+SET\s+.+?\s+WHERE\s+(.+)$",
                query, re.IGNORECASE | re.DOTALL,
            )
            return m.group(1).strip() if m else ""

        return ""

    @staticmethod
    def _parse_set_fields(query: str) -> List[tuple]:
        """Parse SET clause from an UPDATE query.

        Returns:
            List of (field_name, proposed_value) tuples.
            proposed_value is extracted from literals or marked as
            ``"<placeholder>"`` for parameterised queries.
        """
        import re
        m = re.match(
            r"^\s*UPDATE\s+\w+\s+SET\s+(.+?)(?:\s+WHERE\s+.+)?$",
            query, re.IGNORECASE | re.DOTALL,
        )
        if not m:
            return []

        set_clause = m.group(1).strip()
        fields: List[tuple] = []

        for assignment in set_clause.split(","):
            assignment = assignment.strip()
            eq_match = re.match(r"(\w+)\s*=\s*(.+)", assignment)
            if eq_match:
                field_name = eq_match.group(1)
                value_str = eq_match.group(2).strip()
                # Try to extract literal value
                if value_str == "?":
                    fields.append((field_name, "<placeholder>"))
                elif value_str.startswith("'") and value_str.endswith("'"):
                    fields.append((field_name, value_str[1:-1]))
                else:
                    try:
                        fields.append((field_name, int(value_str)))
                    except ValueError:
                        try:
                            fields.append((field_name, float(value_str)))
                        except ValueError:
                            fields.append((field_name, value_str))

        return fields

    @staticmethod
    def _count_placeholders_in_set(query: str) -> int:
        """Count the number of ``?`` placeholders in the SET clause."""
        import re
        m = re.match(
            r"^\s*UPDATE\s+\w+\s+SET\s+(.+?)(?:\s+WHERE\s+.+)?$",
            query, re.IGNORECASE | re.DOTALL,
        )
        if not m:
            return 0
        return m.group(1).count("?")

    @staticmethod
    def _parse_insert_columns(query: str) -> List[str]:
        """Parse column names from an INSERT query.

        Returns:
            List of column names.
        """
        import re
        m = re.match(
            r"^\s*INSERT\s+INTO\s+\w+\s*\(([^)]+)\)",
            query, re.IGNORECASE,
        )
        if not m:
            return []
        cols_str = m.group(1)
        return [c.strip().strip('"').strip("'") for c in cols_str.split(",")]

    @staticmethod
    def _build_db_summary(
        operation: str,
        table: str,
        affected_rows: int,
        diffs: List[DiffEntry],
    ) -> str:
        """Build a human-readable summary for a DB diff."""
        if not diffs:
            return f"DB {operation} on {table}: no changes detected"

        removed = sum(1 for d in diffs if d.change_type == "removed")
        added = sum(1 for d in diffs if d.change_type == "added")
        modified = sum(1 for d in diffs if d.change_type == "modified")

        parts: List[str] = [f"DB {operation} on {table}:"]
        if added:
            parts.append(f"{added} field(s) added")
        if modified:
            parts.append(f"{modified} field(s) modified")
        if removed:
            parts.append(f"{removed} field(s) removed")

        if affected_rows > 0:
            parts.append(f"({affected_rows} row(s) affected)")

        return " ".join(parts)


# ──────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────

def _truncate(value: Any, max_len: int = 50) -> str:
    """Truncate a value representation for display."""
    s = str(value)
    if len(s) > max_len:
        return s[:max_len - 3] + "..."
    return s


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_instance: Optional[DiffPreviewEngine] = None
_instance_lock = threading.Lock()


def get_diff_preview_engine() -> DiffPreviewEngine:
    """Return the singleton DiffPreviewEngine instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DiffPreviewEngine()
    return _instance


def reset_diff_preview_engine() -> None:
    """Reset the singleton instance (mainly for testing)."""
    global _instance
    with _instance_lock:
        _instance = None
