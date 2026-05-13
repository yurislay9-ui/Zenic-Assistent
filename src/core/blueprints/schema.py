"""
Zenic-Agents Asistente - Blueprint Schema (Phase 5)

Enhanced Blueprint schema with certified Blueprints support.
Extends the existing blueprint_schema.py with:
  - DB schema definitions (entities, fields, indexes)
  - SNA monitor hooks (structured, not just dicts)
  - ECDSA certification
  - Compatibility validation
  - Tier-based access control
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Set

from .types import (
    ActionTemplateDef, BlueprintCompatibility, BlueprintMetadataV2,
    BlueprintSignature, BlueprintStatus, BlueprintTier,
    BusinessRuleDef, DBEntitySchema, DBFieldSchema, DBSchema,
    FieldType, MonitorHook, ConflictStrategy,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  CERTIFIED BLUEPRINT
# ──────────────────────────────────────────────────────────────

class CertifiedBlueprint:
    """A certified, composable Blueprint for domain parameterization.

    This is the Phase 5 enhanced version that includes DB schema,
    structured monitor hooks, ECDSA certification, and compatibility
    tracking. Replaces the simple Blueprint dataclass.

    Usage:
        bp = CertifiedBlueprint(
            metadata=BlueprintMetadataV2(name="retail_inventory", domain="retail"),
        )
        bp.add_entity(DBEntitySchema(name="Product", fields=[...]))
        bp.add_monitor_hook(MonitorHook(monitor_id="low_stock", ...))
        bp.add_rule(BusinessRuleDef(...))
    """

    def __init__(
        self,
        metadata: BlueprintMetadataV2,
        db_schema: Optional[DBSchema] = None,
        executor_schemas: Optional[Dict[str, Any]] = None,
        rules: Optional[List[BusinessRuleDef]] = None,
        actions: Optional[List[ActionTemplateDef]] = None,
        monitor_hooks: Optional[List[MonitorHook]] = None,
    ) -> None:
        self.metadata: BlueprintMetadataV2 = metadata
        self.db_schema: DBSchema = db_schema or DBSchema()
        self.executor_schemas: Dict[str, Any] = executor_schemas or {}
        self.rules: List[BusinessRuleDef] = rules or []
        self.actions: List[ActionTemplateDef] = actions or []
        self.monitor_hooks: List[MonitorHook] = monitor_hooks or []

    # ── Entity Management ──────────────────────────────────

    def add_entity(self, entity: DBEntitySchema) -> None:
        """Add a database entity to the Blueprint's schema."""
        existing_names = {e.name for e in self.db_schema.entities}
        if entity.name in existing_names:
            logger.warning(
                "CertifiedBlueprint: Entity '%s' already exists, replacing",
                entity.name,
            )
            self.db_schema.entities = [
                e for e in self.db_schema.entities if e.name != entity.name
            ]
        self.db_schema.entities.append(entity)

    def get_entity(self, name: str) -> Optional[DBEntitySchema]:
        """Get a database entity by name."""
        for entity in self.db_schema.entities:
            if entity.name == name:
                return entity
        return None

    def get_entity_names(self) -> List[str]:
        """Get all entity names in the DB schema."""
        return [e.name for e in self.db_schema.entities]

    # ── Monitor Hook Management ────────────────────────────

    def add_monitor_hook(self, hook: MonitorHook) -> None:
        """Add an SNA monitor hook to the Blueprint."""
        existing_ids = {h.monitor_id for h in self.monitor_hooks}
        if hook.monitor_id in existing_ids:
            logger.debug(
                "CertifiedBlueprint: Monitor hook '%s' replaced",
                hook.monitor_id,
            )
            self.monitor_hooks = [
                h for h in self.monitor_hooks
                if h.monitor_id != hook.monitor_id
            ]
        self.monitor_hooks.append(hook)

    def get_monitor_hooks_dict(self) -> Dict[str, Dict[str, Any]]:
        """Convert monitor hooks to the format expected by SNA ThresholdEngine.

        Returns the same format as Blueprint.monitor_hooks for
        backward compatibility with ThresholdEngine.load_from_blueprint_hooks().
        """
        result: Dict[str, Dict[str, Any]] = {}
        for hook in self.monitor_hooks:
            result[hook.monitor_id] = {
                "weight": hook.weight,
                "interval_seconds": hook.interval_seconds,
                "enabled": hook.enabled,
                "thresholds": hook.thresholds,
                "params": hook.params,
                "notification_channel": hook.notification_channel,
            }
        return result

    # ── Rule & Action Management ───────────────────────────

    def add_rule(self, rule: BusinessRuleDef) -> None:
        """Add a business rule to the Blueprint."""
        self.rules.append(rule)

    def add_action(self, action: ActionTemplateDef) -> None:
        """Add an action template to the Blueprint."""
        existing = {a.template_id for a in self.actions}
        if action.template_id in existing:
            self.actions = [
                a for a in self.actions if a.template_id != action.template_id
            ]
        self.actions.append(action)

    def get_action_by_name(self, name: str) -> Optional[ActionTemplateDef]:
        """Get an action template by name."""
        for action in self.actions:
            if action.name == name:
                return action
        return None

    # ── Compatibility ──────────────────────────────────────

    def is_compatible_with(self, other_name: str, version: str = "*") -> bool:
        """Check if this Blueprint is compatible with another."""
        for compat in self.metadata.compatibility:
            if compat.blueprint_name == other_name:
                return _check_version_range(version, compat.version_range)
        return True  # No explicit incompatibility declared

    def get_known_conflicts(self, other_name: str) -> List[str]:
        """Get known conflicts with another Blueprint."""
        for compat in self.metadata.compatibility:
            if compat.blueprint_name == other_name:
                return compat.known_conflicts
        return []

    # ── Certification ──────────────────────────────────────

    @property
    def is_certified(self) -> bool:
        """Check if this Blueprint has a valid ECDSA signature."""
        return (
            self.metadata.signature is not None
            and bool(self.metadata.signature.signature_hex)
            and self.metadata.status == BlueprintStatus.CERTIFIED
        )

    @property
    def tier(self) -> BlueprintTier:
        """Get the Blueprint's access tier."""
        return self.metadata.tier

    # ── Fingerprint ────────────────────────────────────────

    def content_hash(self) -> str:
        """Compute SHA-256 hash of all Blueprint content.

        Used for signature verification and cache invalidation.
        Excludes signature itself from the hash.
        """
        content = self.to_dict(include_signature=False)
        canonical = json.dumps(content, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ── Serialization ──────────────────────────────────────

    def to_dict(self, include_signature: bool = True) -> Dict[str, Any]:
        """Serialize the Blueprint to a dictionary."""
        result: Dict[str, Any] = {
            "metadata": _metadata_to_dict(self.metadata, include_signature),
            "db_schema": _dbschema_to_dict(self.db_schema),
            "executors": self.executor_schemas,
            "rules": [_rule_to_dict(r) for r in self.rules],
            "actions": {_action_to_key(a): _action_to_dict(a) for a in self.actions},
            "monitors": {
                h.monitor_id: _monitor_hook_to_dict(h) for h in self.monitor_hooks
            },
        }
        return result

    # ── Stats ──────────────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        """Get Blueprint statistics summary."""
        return {
            "name": self.metadata.name,
            "version": self.metadata.version,
            "domain": self.metadata.domain,
            "tier": self.metadata.tier.value,
            "status": self.metadata.status.value,
            "is_certified": self.is_certified,
            "entities": len(self.db_schema.entities),
            "total_fields": sum(
                len(e.fields) for e in self.db_schema.entities
            ),
            "rules": len(self.rules),
            "actions": len(self.actions),
            "monitors": len(self.monitor_hooks),
            "compatibilities": len(self.metadata.compatibility),
        }


# ──────────────────────────────────────────────────────────────
#  SERIALIZATION HELPERS
# ──────────────────────────────────────────────────────────────

def _metadata_to_dict(
    meta: BlueprintMetadataV2, include_signature: bool = True,
) -> Dict[str, Any]:
    """Convert metadata to dict."""
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
    }
    if include_signature and meta.signature:
        result["signature"] = {
            "algorithm": meta.signature.algorithm,
            "signature_hex": meta.signature.signature_hex,
            "public_key_hex": meta.signature.public_key_hex,
            "signed_at": meta.signature.signed_at,
            "signer_id": meta.signature.signer_id,
            "certificate_id": meta.signature.certificate_id,
        }
    if meta.compatibility:
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


# ──────────────────────────────────────────────────────────────
#  VERSION RANGE CHECK (simplified semver)
# ──────────────────────────────────────────────────────────────

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
