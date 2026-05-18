"""
ZENIC-AGENTS - Diff Preview Data Models

Defines the core data structures used by the Diff Preview Engine:
* DiffEntry  – a single field-level diff
* DiffResult – the aggregated result of a diff preview
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


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
