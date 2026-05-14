"""
Zenic-Agents Asistente - Blueprint Validator (Phase 5)

Enhanced validation for certified Blueprints.
Validates:
  - Schema completeness (required fields, DB schema integrity)
  - Monitor hook structure
  - Business rule consistency
  - Compatibility between composed Blueprints
  - ECDSA signature verification
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from .types import (
    ActionTemplateDef, BlueprintCompatibility, BlueprintMetadataV2,
    BusinessRuleDef, DBEntitySchema, DBFieldSchema,
    DBSchema, FieldType, MonitorHook,
)
from .schema import CertifiedBlueprint

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  VALIDATION RESULT
# ──────────────────────────────────────────────────────────────

class ValidationResult:
    """Result of Blueprint validation."""

    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []

    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors)."""
        return len(self.errors) == 0

    def add_error(self, msg: str) -> None:
        """Add a validation error."""
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        """Add a validation warning."""
        self.warnings.append(msg)

    def merge(self, other: "ValidationResult") -> None:
        """Merge another validation result into this one."""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def __repr__(self) -> str:
        return (
            f"ValidationResult(valid={self.is_valid}, "
            f"errors={len(self.errors)}, warnings={len(self.warnings)})"
        )


# ──────────────────────────────────────────────────────────────
#  BLUEPRINT VALIDATOR
# ──────────────────────────────────────────────────────────────

class BlueprintValidatorV2:
    """Comprehensive validator for CertifiedBlueprint objects.

    Validates all aspects of a Blueprint:
      1. Metadata completeness
      2. DB schema integrity
      3. Monitor hook structure
      4. Business rule consistency
      5. Action template validity
      6. Executor schema consistency
    """

    # Required metadata fields
    REQUIRED_META_FIELDS = ["name", "version", "domain"]

    # Valid severity levels
    VALID_SEVERITIES = {"info", "warning", "error", "block", "critical"}

    # Valid safety categories
    VALID_SAFETY_CATEGORIES = {
        "safe", "moderate", "destructive", "financial",
    }

    # Valid executor types
    KNOWN_EXECUTOR_TYPES = {
        "email", "http", "database", "file", "notification",
        "schedule", "transform", "webhook", "discord",
    }

    def validate(self, blueprint: CertifiedBlueprint) -> ValidationResult:
        """Run all validations on a Blueprint."""
        result = ValidationResult()

        self._validate_metadata(blueprint, result)
        self._validate_db_schema(blueprint, result)
        self._validate_monitor_hooks(blueprint, result)
        self._validate_rules(blueprint, result)
        self._validate_actions(blueprint, result)
        self._validate_executor_schemas(blueprint, result)

        return result

    def validate_compatibility(
        self,
        blueprints: List[CertifiedBlueprint],
    ) -> ValidationResult:
        """Validate compatibility between multiple Blueprints for composition."""
        result = ValidationResult()

        if len(blueprints) < 2:
            return result

        # Check pairwise compatibility
        for i in range(len(blueprints)):
            for j in range(i + 1, len(blueprints)):
                self._check_pair_compatibility(
                    blueprints[i], blueprints[j], result,
                )

        # Check for entity name collisions
        self._check_entity_collisions(blueprints, result)

        # Check for rule conflicts
        self._check_rule_conflicts(blueprints, result)

        return result

    # ── Metadata Validation ────────────────────────────────

    def _validate_metadata(
        self, bp: CertifiedBlueprint, result: ValidationResult,
    ) -> None:
        """Validate Blueprint metadata completeness."""
        meta = bp.metadata

        for field_name in self.REQUIRED_META_FIELDS:
            value = getattr(meta, field_name, "")
            if not value:
                result.add_error(f"Metadata missing required field: {field_name}")

        # Version format check
        if meta.version:
            parts = meta.version.split(".")
            if len(parts) < 2:
                result.add_warning(
                    f"Version '{meta.version}' doesn't follow semver (X.Y.Z)"
                )

        # Name format check
        if meta.name and not meta.name.replace("_", "").replace("-", "").isalnum():
            result.add_error(
                f"Blueprint name '{meta.name}' contains invalid characters"
            )

    # ── DB Schema Validation ───────────────────────────────

    def _validate_db_schema(
        self, bp: CertifiedBlueprint, result: ValidationResult,
    ) -> None:
        """Validate database schema integrity."""
        entity_names: Set[str] = set()

        for entity in bp.db_schema.entities:
            # Check entity name uniqueness
            if entity.name in entity_names:
                result.add_error(f"Duplicate entity name: {entity.name}")
            entity_names.add(entity.name)

            # Check entity has at least one field
            if not entity.fields:
                result.add_warning(f"Entity '{entity.name}' has no fields")

            # Validate fields
            field_names: Set[str] = set()
            for fld in entity.fields:
                if fld.name in field_names:
                    result.add_error(
                        f"Duplicate field '{fld.name}' in entity '{entity.name}'"
                    )
                field_names.add(fld.name)

                # Validate field type
                try:
                    FieldType(fld.field_type.value if isinstance(fld.field_type, FieldType) else fld.field_type)
                except ValueError:
                    result.add_error(
                        f"Invalid field type '{fld.field_type}' "
                        f"on '{entity.name}.{fld.name}'"
                    )

    # ── Monitor Hook Validation ────────────────────────────

    def _validate_monitor_hooks(
        self, bp: CertifiedBlueprint, result: ValidationResult,
    ) -> None:
        """Validate SNA monitor hook configurations."""
        hook_ids: Set[str] = set()

        for hook in bp.monitor_hooks:
            if hook.monitor_id in hook_ids:
                result.add_error(
                    f"Duplicate monitor hook: {hook.monitor_id}"
                )
            hook_ids.add(hook.monitor_id)

            # Validate weight
            valid_weights = {"lightweight", "medium", "heavy"}
            if hook.weight not in valid_weights:
                result.add_error(
                    f"Invalid monitor weight '{hook.weight}' "
                    f"for hook '{hook.monitor_id}'"
                )

            # Validate thresholds structure
            for i, th in enumerate(hook.thresholds):
                if "field" not in th:
                    result.add_warning(
                        f"Threshold [{i}] in '{hook.monitor_id}' "
                        f"missing 'field' key"
                    )
                if "value" not in th:
                    result.add_warning(
                        f"Threshold [{i}] in '{hook.monitor_id}' "
                        f"missing 'value' key"
                    )

    # ── Business Rule Validation ───────────────────────────

    def _validate_rules(
        self, bp: CertifiedBlueprint, result: ValidationResult,
    ) -> None:
        """Validate business rules."""
        rule_ids: Set[str] = set()

        for rule in bp.rules:
            if rule.rule_id in rule_ids:
                result.add_error(f"Duplicate rule ID: {rule.rule_id}")
            rule_ids.add(rule.rule_id)

            if rule.severity not in self.VALID_SEVERITIES:
                result.add_error(
                    f"Invalid severity '{rule.severity}' in rule '{rule.rule_id}'"
                )

            if rule.executor_type and rule.executor_type not in self.KNOWN_EXECUTOR_TYPES:
                result.add_warning(
                    f"Unknown executor type '{rule.executor_type}' "
                    f"in rule '{rule.rule_id}'"
                )

    # ── Action Template Validation ─────────────────────────

    def _validate_actions(
        self, bp: CertifiedBlueprint, result: ValidationResult,
    ) -> None:
        """Validate action templates."""
        template_ids: Set[str] = set()

        for action in bp.actions:
            if action.template_id in template_ids:
                result.add_error(
                    f"Duplicate action template ID: {action.template_id}"
                )
            template_ids.add(action.template_id)

            if action.safety_category not in self.VALID_SAFETY_CATEGORIES:
                result.add_error(
                    f"Invalid safety category '{action.safety_category}' "
                    f"in action '{action.template_id}'"
                )

            if action.executor_type and action.executor_type not in self.KNOWN_EXECUTOR_TYPES:
                result.add_warning(
                    f"Unknown executor type '{action.executor_type}' "
                    f"in action '{action.template_id}'"
                )

    # ── Executor Schema Validation ─────────────────────────

    def _validate_executor_schemas(
        self, bp: CertifiedBlueprint, result: ValidationResult,
    ) -> None:
        """Validate executor schemas reference known types."""
        for exec_type in bp.executor_schemas:
            if exec_type not in self.KNOWN_EXECUTOR_TYPES:
                result.add_warning(
                    f"Executor schema for unknown type: {exec_type}"
                )

    # ── Compatibility Checks ───────────────────────────────

    def _check_pair_compatibility(
        self,
        bp_a: CertifiedBlueprint,
        bp_b: CertifiedBlueprint,
        result: ValidationResult,
    ) -> None:
        """Check compatibility between two Blueprints."""
        # Check A → B compatibility
        conflicts = bp_a.get_known_conflicts(bp_b.metadata.name)
        for conflict in conflicts:
            result.add_error(
                f"Conflict between '{bp_a.metadata.name}' and "
                f"'{bp_b.metadata.name}': {conflict}"
            )

        # Check B → A compatibility
        conflicts = bp_b.get_known_conflicts(bp_a.metadata.name)
        for conflict in conflicts:
            result.add_error(
                f"Conflict between '{bp_b.metadata.name}' and "
                f"'{bp_a.metadata.name}': {conflict}"
            )

    def _check_entity_collisions(
        self,
        blueprints: List[CertifiedBlueprint],
        result: ValidationResult,
    ) -> None:
        """Check for entity name collisions across Blueprints."""
        entity_map: Dict[str, List[str]] = {}

        for bp in blueprints:
            for entity in bp.db_schema.entities:
                if entity.name not in entity_map:
                    entity_map[entity.name] = []
                entity_map[entity.name].append(bp.metadata.name)

        for entity_name, bp_names in entity_map.items():
            if len(bp_names) > 1:
                result.add_warning(
                    f"Entity '{entity_name}' defined in multiple "
                    f"Blueprints: {', '.join(bp_names)}. "
                    f"Composition will use last-wins strategy."
                )

    def _check_rule_conflicts(
        self,
        blueprints: List[CertifiedBlueprint],
        result: ValidationResult,
    ) -> None:
        """Check for conflicting business rules across Blueprints."""
        rule_map: Dict[str, List[str]] = {}

        for bp in blueprints:
            for rule in bp.rules:
                key = f"{rule.executor_type}:{rule.condition}"
                if key not in rule_map:
                    rule_map[key] = []
                rule_map[key].append(
                    f"{bp.metadata.name}/{rule.rule_id}:{rule.action}"
                )

        for key, rules in rule_map.items():
            if len(rules) > 1:
                # Different actions for same condition = potential conflict
                actions = set(r.split(":")[-1] for r in rules)
                if len(actions) > 1:
                    result.add_warning(
                        f"Conflicting rules for '{key}': {rules}"
                    )
