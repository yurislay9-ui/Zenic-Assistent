"""
Zenic-Agents Asistente - Dispatch Blueprint Integration (Phase 5)

Mixin that adds Phase 5 Blueprint Registry integration
to the ActionDispatcher. Extracted from dispatch_action.py
to keep the main file under 400 lines.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.blueprints import CertifiedBlueprint
    from ..blueprint_schema import Blueprint

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  BLUEPRINT BRIDGE MIXIN
# ──────────────────────────────────────────────────────────────

class BlueprintBridgeMixin:
    """Mixin for ActionDispatcher that provides Blueprint Registry integration.

    Methods:
      - set_blueprint: Set the active Blueprint directly
      - set_blueprint_from_registry: Load from Blueprint Registry
      - _certified_to_legacy: Convert CertifiedBlueprint → legacy Blueprint
    """

    def set_blueprint(self, blueprint: "Blueprint") -> None:
        """Set the active Blueprint for validation (Phase 5)."""
        self._blueprint = blueprint

    def set_blueprint_from_registry(
        self, blueprint_name: str = "", tenant_id: str = "",
    ) -> bool:
        """Load active Blueprint from the Blueprint Registry (Phase 5).

        If blueprint_name is given, loads that specific Blueprint.
        If only tenant_id is given, loads the tenant's composed Blueprint.
        """
        try:
            from src.core.blueprints import get_blueprint_registry
            reg = get_blueprint_registry()

            bp = None
            if blueprint_name:
                bp = reg.get(blueprint_name)
            elif tenant_id:
                bp = reg.get_tenant_blueprint(tenant_id)

            if bp is None:
                return False

            legacy_bp = self._certified_to_legacy(bp)
            self._blueprint = legacy_bp
            return True
        except Exception:
            return False

    def _certified_to_legacy(
        self, certified: "CertifiedBlueprint",
    ) -> "Blueprint":
        """Convert a CertifiedBlueprint (Phase 5) to legacy Blueprint.

        Maintains backward compatibility with the Phase 3 Blueprint
        dataclass used by BlueprintValidator.
        """
        from ..blueprint_schema import (
            Blueprint, BlueprintMetadata, BusinessRule,
            ActionTemplate, ExecutorSchema,
        )

        # Convert executor schemas
        executor_schemas: Dict[str, Any] = {}
        for exec_type, schema_data in certified.executor_schemas.items():
            if isinstance(schema_data, ExecutorSchema):
                executor_schemas[exec_type] = schema_data
            elif isinstance(schema_data, dict):
                executor_schemas[exec_type] = ExecutorSchema(
                    executor_type=exec_type,
                    required_fields=schema_data.get("required", []),
                    optional_fields=schema_data.get("optional", []),
                    field_types=schema_data.get("types", {}),
                    field_defaults=schema_data.get("defaults", {}),
                    field_validators=schema_data.get("validators", {}),
                    max_records=schema_data.get("max_records", 0),
                    allowed_operations=schema_data.get("allowed_operations", []),
                    denied_operations=schema_data.get("denied_operations", []),
                    rate_limits=schema_data.get("rate_limits", {}),
                )

        # Convert business rules
        business_rules = []
        for rule in certified.rules:
            business_rules.append(BusinessRule(
                name=rule.name,
                description=rule.description,
                executor_type=rule.executor_type,
                condition=rule.condition,
                action=rule.action,
                severity=rule.severity,
            ))

        # Convert action templates
        action_templates: Dict[str, Any] = {}
        for action in certified.actions:
            action_templates[action.template_id] = ActionTemplate(
                name=action.name,
                description=action.description,
                executor_type=action.executor_type,
                config_template=action.config_template,
                safety_category=action.safety_category,
                requires_confirmation=action.requires_confirmation,
                requires_approval=action.requires_approval,
            )

        # Convert monitor hooks to dict format
        monitor_hooks = certified.get_monitor_hooks_dict()

        return Blueprint(
            metadata=BlueprintMetadata(
                name=certified.metadata.name,
                version=certified.metadata.version,
                domain=certified.metadata.domain,
                description=certified.metadata.description,
                author=certified.metadata.author,
            ),
            executor_schemas=executor_schemas,
            business_rules=business_rules,
            action_templates=action_templates,
            monitor_hooks=monitor_hooks,
            compatible_with=[
                c.blueprint_name for c in certified.metadata.compatibility
            ],
        )
