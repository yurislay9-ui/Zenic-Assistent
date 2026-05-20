"""ZENIC-AGENTS - Impact Preview Engine: Conversion Helpers

Converts specialized preview types (DB, File, Email) to the
generic ImpactPreview, and generates generic previews for
unrecognized action types.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..safety_gate import ActionCategory
from ._types import (
    ImpactRiskLevel,
    ImpactField,
    ImpactPreview,
    DBImpactPreview,
    FileImpactPreview,
    EmailImpactPreview,
)


def db_preview_to_impact(
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


def file_preview_to_impact(
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


def email_preview_to_impact(
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


def generic_preview(
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
