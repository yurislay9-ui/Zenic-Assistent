"""Helpers for schema."""

from __future__ import annotations
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Set

from ..types import BlueprintMetadataV2, DBSchema, BusinessRuleDef, ActionTemplateDef, MonitorHook

logger = logging.getLogger(__name__)


def _metadata_to_dict(
    meta: BlueprintMetadataV2, include_signature: bool = True,
) -> Dict[str, Any]:
    """Convert Blueprint metadata to dict."""
    result: Dict[str, Any] = {
        "name": meta.name,
        "version": meta.version,
        "domain": meta.domain,
        "subdomain": meta.subdomain,
        "description": meta.description,
        "author": meta.author,
        "tier": meta.tier.value,
        "status": meta.status.value,
        "tags": meta.tags,
        "icon": meta.icon,
        "scale": meta.scale,
        "created_at": meta.created_at,
        "updated_at": meta.updated_at,
    }
    if include_signature and meta.signature is not None:
        result["signature"] = {
            "algorithm": meta.signature.algorithm,
            "signature_hex": meta.signature.signature_hex,
            "public_key_hex": meta.signature.public_key_hex,
            "signed_at": meta.signature.signed_at,
            "signer_id": meta.signature.signer_id,
            "certificate_id": meta.signature.certificate_id,
        }
    result["compatibility"] = [
        {
            "blueprint_name": c.blueprint_name,
            "version_range": c.version_range,
            "composition_notes": c.composition_notes,
            "known_conflicts": c.known_conflicts,
        }
        for c in meta.compatibility
    ]
    return result


def _dbschema_to_dict(schema: DBSchema) -> Dict[str, Any]:
    """Convert DB schema to dict."""
    return {
        "version": schema.version,
        "entities": [
            {
                "name": e.name,
                "primary_key": e.primary_key,
                "description": e.description,
                "fields": [
                    {
                        "name": f.name,
                        "type": f.field_type.value,
                        "required": f.required,
                        "unique": f.unique,
                        "indexed": f.indexed,
                        "default": f.default,
                        "description": f.description,
                    }
                    for f in e.fields
                ],
                "indexes": e.indexes,
                "constraints": e.constraints,
            }
            for e in schema.entities
        ],
    }



def _rule_to_dict(rule: BusinessRuleDef) -> Dict[str, Any]:
    """Convert a business rule to dict."""
    return {
        "rule_id": rule.rule_id,
        "name": rule.name,
        "description": rule.description,
        "executor_type": rule.executor_type,
        "condition": rule.condition,
        "action": rule.action,
        "severity": rule.severity,
        "active": rule.active,
    }



def _action_to_key(action: ActionTemplateDef) -> str:
    """Get a dict key for an action template."""
    return action.template_id



def _action_to_dict(action: ActionTemplateDef) -> Dict[str, Any]:
    """Convert an action template to dict."""
    return {
        "name": action.name,
        "description": action.description,
        "executor_type": action.executor_type,
        "config": action.config_template,
        "safety_category": action.safety_category,
        "requires_confirmation": action.requires_confirmation,
        "requires_approval": action.requires_approval,
    }



def _monitor_hook_to_dict(hook: MonitorHook) -> Dict[str, Any]:
    """Convert a monitor hook to dict."""
    return {
        "weight": hook.weight,
        "interval_seconds": hook.interval_seconds,
        "enabled": hook.enabled,
        "thresholds": hook.thresholds,
        "params": hook.params,
        "notification_channel": hook.notification_channel,
    }



def _check_version_range(version: str, range_spec: str) -> bool:
    """Check if a version satisfies a range specification.

    Supports simplified semver patterns:
      - "*" → any version
      - ">=1.0.0" → version >= 1.0.0
      - ">=1.0.0,<3.0.0" → between 1.0.0 and 3.0.0
      - "1.0.0" → exact match
    """
    if range_spec == "*":
        return True

    try:
        v_parts = [int(p) for p in version.split(".")]
    except (ValueError, AttributeError):
        return True

    constraints = range_spec.split(",")
    for constraint in constraints:
        constraint = constraint.strip()
        if constraint.startswith(">="):
            target = [int(p) for p in constraint[2:].split(".")]
            if v_parts < target:
                return False
        elif constraint.startswith(">"):
            target = [int(p) for p in constraint[1:].split(".")]
            if v_parts <= target:
                return False
        elif constraint.startswith("<="):
            target = [int(p) for p in constraint[2:].split(".")]
            if v_parts > target:
                return False
        elif constraint.startswith("<"):
            target = [int(p) for p in constraint[1:].split(".")]
            if v_parts >= target:
                return False
        elif constraint.startswith("=="):
            target = [int(p) for p in constraint[2:].split(".")]
            if v_parts != target:
                return False
        else:
            # Exact version match
            try:
                target = [int(p) for p in constraint.split(".")]
                if v_parts != target:
                    return False
            except ValueError:
                pass

    return True
