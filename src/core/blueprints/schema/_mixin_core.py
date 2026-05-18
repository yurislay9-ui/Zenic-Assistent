"""Core logic for schema."""

from __future__ import annotations
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Set

from ..types import BlueprintMetadataV2, BlueprintStatus, BlueprintTier, DBSchema, DBEntitySchema, BusinessRuleDef, ActionTemplateDef, MonitorHook
from ._types import *
from ._helpers import _metadata_to_dict, _dbschema_to_dict, _rule_to_dict, _action_to_key, _action_to_dict, _monitor_hook_to_dict, _check_version_range

logger = logging.getLogger(__name__)

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
