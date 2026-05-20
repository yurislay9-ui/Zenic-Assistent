"""ZENIC-AGENTS - Impact Preview Engine: Types and Dataclasses"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

from ..safety_gate import ActionCategory

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

