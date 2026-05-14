"""
Zenic-Agents Asistente - Blueprint Composer (Phase 5)

Composes multiple Blueprints into a single unified Blueprint.
Handles:
  - Schema merging (entities, fields)
  - Rule aggregation with conflict detection
  - Monitor hook composition
  - Action template merging
  - Compatibility validation before composition
  - Conflict resolution strategies
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from .types import (
    ActionTemplateDef, BlueprintCompatibility, BlueprintMetadataV2,
    BlueprintSignature, BlueprintStatus, BlueprintTier,
    BusinessRuleDef, ConflictStrategy,
    DBEntitySchema, DBFieldSchema, DBSchema, MonitorHook,
)
from .schema import CertifiedBlueprint
from .validator import BlueprintValidatorV2, ValidationResult
from .certifier import certify_blueprint

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  COMPOSITION RESULT
# ──────────────────────────────────────────────────────────────

class CompositionResult:
    """Result of a Blueprint composition operation."""

    def __init__(self) -> None:
        self.blueprint: Optional[CertifiedBlueprint] = None
        self.validation: ValidationResult = ValidationResult()
        self.warnings: List[str] = []
        self.source_names: List[str] = []
        self.conflicts_resolved: int = 0

    @property
    def success(self) -> bool:
        """Check if composition succeeded."""
        return self.blueprint is not None and self.validation.is_valid


# ──────────────────────────────────────────────────────────────
#  BLUEPRINT COMPOSER
# ──────────────────────────────────────────────────────────────

class BlueprintComposer:
    """Composes multiple Blueprints into a single unified Blueprint.

    Usage:
        composer = BlueprintComposer()
        result = composer.compose([retail_bp, invoice_bp])
        if result.success:
            combined = result.blueprint
    """

    def __init__(
        self,
        conflict_strategy: ConflictStrategy = ConflictStrategy.LAST_WINS,
        validate_before: bool = True,
        certify_after: bool = False,
    ) -> None:
        self._strategy = conflict_strategy
        self._validate_before = validate_before
        self._certify_after = certify_after
        self._validator = BlueprintValidatorV2()

    def compose(
        self,
        blueprints: List[CertifiedBlueprint],
        composed_name: str = "",
        signer_id: str = "",
    ) -> CompositionResult:
        """Compose multiple Blueprints into one.

        Args:
            blueprints: List of Blueprints to compose.
            composed_name: Optional name for the composed Blueprint.
            signer_id: Signer ID if certifying after composition.

        Returns:
            CompositionResult with the composed Blueprint and validation info.
        """
        result = CompositionResult()
        result.source_names = [bp.metadata.name for bp in blueprints]

        if not blueprints:
            result.warnings.append("No Blueprints provided for composition")
            return result

        # Pre-composition validation
        if self._validate_before and len(blueprints) > 1:
            compat_result = self._validator.validate_compatibility(blueprints)
            result.validation.merge(compat_result)
            if not compat_result.is_valid:
                logger.warning(
                    "Composer: Compatibility validation found %d errors",
                    len(compat_result.errors),
                )

        # Build composed metadata
        metadata = self._compose_metadata(blueprints, composed_name)

        # Build composed DB schema
        db_schema, conflicts = self._compose_db_schema(blueprints)
        result.conflicts_resolved = conflicts

        # Build composed executor schemas
        executor_schemas = self._compose_executor_schemas(blueprints)

        # Build composed rules
        rules = self._compose_rules(blueprints)

        # Build composed actions
        actions, action_conflicts = self._compose_actions(blueprints)
        result.conflicts_resolved += action_conflicts

        # Build composed monitor hooks
        monitor_hooks, monitor_conflicts = self._compose_monitor_hooks(blueprints)
        result.conflicts_resolved += monitor_conflicts

        # Create composed Blueprint
        composed = CertifiedBlueprint(
            metadata=metadata,
            db_schema=db_schema,
            executor_schemas=executor_schemas,
            rules=rules,
            actions=actions,
            monitor_hooks=monitor_hooks,
        )

        # Post-composition validation
        post_result = self._validator.validate(composed)
        result.validation.merge(post_result)

        # Certify if requested
        if self._certify_after and post_result.is_valid:
            try:
                certify_blueprint(composed)
            except Exception as e:
                result.warnings.append(f"Certification failed: {e}")

        result.blueprint = composed
        return result

    # ── Metadata Composition ───────────────────────────────

    def _compose_metadata(
        self,
        blueprints: List[CertifiedBlueprint],
        composed_name: str,
    ) -> BlueprintMetadataV2:
        """Compose metadata from multiple Blueprints."""
        names = [bp.metadata.name for bp in blueprints]
        name = composed_name or "+".join(names)

        # Take highest tier
        tier_order = {
            BlueprintTier.FREE: 0,
            BlueprintTier.PRO: 1,
            BlueprintTier.ENTERPRISE: 2,
            BlueprintTier.PARTNER: 3,
        }
        max_tier = max(
            blueprints, key=lambda bp: tier_order.get(bp.metadata.tier, 0)
        ).metadata.tier

        # Collect all domains
        domains = list({bp.metadata.domain for bp in blueprints if bp.metadata.domain})
        domain = domains[0] if len(domains) == 1 else "composed"

        # Collect all tags
        all_tags: List[str] = []
        for bp in blueprints:
            all_tags.extend(bp.metadata.tags)
        tags = list(dict.fromkeys(all_tags))  # Deduplicated, order-preserved

        # Collect all compatibilities
        all_compat: List[BlueprintCompatibility] = []
        for bp in blueprints:
            all_compat.extend(bp.metadata.compatibility)

        return BlueprintMetadataV2(
            name=name,
            version="1.0.0",
            domain=domain,
            description=f"Composed from: {', '.join(names)}",
            author="composer",
            tier=max_tier,
            status=BlueprintStatus.DRAFT,
            compatibility=all_compat,
            tags=tags,
            scale=blueprints[0].metadata.scale,
        )

    # ── DB Schema Composition ──────────────────────────────

    def _compose_db_schema(
        self, blueprints: List[CertifiedBlueprint],
    ) -> tuple:
        """Compose database schemas from multiple Blueprints.

        Returns (DBSchema, conflicts_resolved_count).
        """
        entity_map: Dict[str, DBEntitySchema] = {}
        conflicts = 0

        for bp in blueprints:
            for entity in bp.db_schema.entities:
                if entity.name in entity_map:
                    conflicts += 1
                    entity_map[entity.name] = self._merge_entity(
                        entity_map[entity.name], entity,
                    )
                else:
                    entity_map[entity.name] = entity

        return DBSchema(entities=list(entity_map.values())), conflicts

    def _merge_entity(
        self, existing: DBEntitySchema, new: DBEntitySchema,
    ) -> DBEntitySchema:
        """Merge two entity schemas based on conflict strategy."""
        if self._strategy == ConflictStrategy.FIRST_WINS:
            return existing
        if self._strategy == ConflictStrategy.LAST_WINS:
            return new
        if self._strategy == ConflictStrategy.FAIL:
            raise ValueError(
                f"Entity conflict: {existing.name} — "
                f"FAIL strategy aborts composition"
            )

        # MERGE strategy: combine fields
        field_map: Dict[str, DBFieldSchema] = {}
        for fld in existing.fields:
            field_map[fld.name] = fld
        for fld in new.fields:
            if fld.name in field_map:
                # Last wins for field conflicts within merge
                field_map[fld.name] = fld
            else:
                field_map[fld.name] = fld

        return DBEntitySchema(
            name=existing.name,
            fields=list(field_map.values()),
            primary_key=existing.primary_key,
            indexes=existing.indexes + new.indexes,
            constraints=list(set(existing.constraints + new.constraints)),
            description=new.description or existing.description,
        )

    # ── Executor Schema Composition ────────────────────────

    def _compose_executor_schemas(
        self, blueprints: List[CertifiedBlueprint],
    ) -> Dict[str, Any]:
        """Compose executor schemas (last-wins for conflicts)."""
        result: Dict[str, Any] = {}
        for bp in blueprints:
            result.update(bp.executor_schemas)
        return result

    # ── Rules Composition ──────────────────────────────────

    def _compose_rules(
        self, blueprints: List[CertifiedBlueprint],
    ) -> List[BusinessRuleDef]:
        """Compose business rules (all appended, deduplicated by rule_id)."""
        seen_ids: set = set()
        rules: List[BusinessRuleDef] = []
        for bp in blueprints:
            for rule in bp.rules:
                if rule.rule_id not in seen_ids:
                    rules.append(rule)
                    seen_ids.add(rule.rule_id)
        return rules

    # ── Actions Composition ────────────────────────────────

    def _compose_actions(
        self, blueprints: List[CertifiedBlueprint],
    ) -> tuple:
        """Compose action templates. Returns (actions, conflicts)."""
        action_map: Dict[str, ActionTemplateDef] = {}
        conflicts = 0

        for bp in blueprints:
            for action in bp.actions:
                if action.template_id in action_map:
                    conflicts += 1
                    if self._strategy != ConflictStrategy.FIRST_WINS:
                        action_map[action.template_id] = action
                else:
                    action_map[action.template_id] = action

        return list(action_map.values()), conflicts

    # ── Monitor Hooks Composition ──────────────────────────

    def _compose_monitor_hooks(
        self, blueprints: List[CertifiedBlueprint],
    ) -> tuple:
        """Compose monitor hooks. Returns (hooks, conflicts)."""
        hook_map: Dict[str, MonitorHook] = {}
        conflicts = 0

        for bp in blueprints:
            for hook in bp.monitor_hooks:
                if hook.monitor_id in hook_map:
                    conflicts += 1
                    if self._strategy != ConflictStrategy.FIRST_WINS:
                        hook_map[hook.monitor_id] = hook
                else:
                    hook_map[hook.monitor_id] = hook

        return list(hook_map.values()), conflicts
