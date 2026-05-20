"""Legacy dict-based conversion methods for NicheConverter."""

from __future__ import annotations
import logging
import re
from typing import Any, Dict, List, Optional

from ..types import BlueprintTier, BlueprintMetadataV2, DBSchema, DBEntitySchema, DBFieldSchema, BusinessRuleDef, ActionTemplateDef, MonitorHook
from ..convert_parts import BLOCK_EXECUTOR_MAP, parse_entity_fields, map_trigger_to_monitor, determine_monitor_weight, determine_notification_channel
from ..schema import CertifiedBlueprint
from ._types import _SENSITIVITY_TIER_MAP

logger = logging.getLogger(__name__)


class NicheConverterLegacyMixin:
    """Legacy dict-based conversion methods.

    These methods support the old YAML-dict path for backward
    compatibility.  New code should prefer ``convert_from_catalog``
    and ``convert_all_from_catalog`` on the main NicheConverter.
    """

    # ── Legacy Dict-Based Conversion (still supported) ──────

    def convert_dict(self, data: Dict[str, Any]) -> Optional[CertifiedBlueprint]:
        """Convert a Niche YAML dict to a CertifiedBlueprint (legacy path).

        This method is kept for backward compatibility with any code
        that still produces dict-based niche data. For new code, use
        convert_from_catalog() or convert_all_from_catalog().
        """
        niche = data.get("niche", {})
        if not niche:
            logger.error("NicheConverter: Missing 'niche' section")
            return None

        metadata = self._build_metadata(niche, data)
        db_schema = self._build_db_schema(data.get("entities", []))
        executor_schemas = self._build_executor_schemas(data.get("composition", {}))
        rules = self._build_rules(data.get("risk_assessment", {}))
        actions = self._build_actions(niche.get("name", ""), data.get("features", {}))
        monitor_hooks = self._build_monitor_hooks(data.get("workflow", {}), niche.get("domain", ""))

        return CertifiedBlueprint(
            metadata=metadata,
            db_schema=db_schema,
            executor_schemas=executor_schemas,
            rules=rules,
            actions=actions,
            monitor_hooks=monitor_hooks,
        )

    # ── Legacy Builder Methods (dict-based) ─────────────────

    def _build_metadata(
        self, niche: Dict[str, Any], data: Dict[str, Any],
    ) -> BlueprintMetadataV2:
        """Build Blueprint metadata from Niche YAML dict (legacy)."""
        risk = data.get("risk_assessment", {})
        sensitivity = risk.get("data_sensitivity", "medium")
        return BlueprintMetadataV2(
            name=niche.get("name", "unnamed"),
            version="1.0.0",
            domain=niche.get("domain", ""),
            subdomain=niche.get("subdomain", ""),
            description=niche.get("description", ""),
            author="zenic-agents",
            tier=_SENSITIVITY_TIER_MAP.get(sensitivity, BlueprintTier.FREE),
            tags=[niche.get("domain", "")],
            scale=niche.get("scale", "medium"),
        )

    def _build_db_schema(self, entities_data: List[Any]) -> DBSchema:
        """Build DB schema from Niche entities (legacy)."""
        entities: List[DBEntitySchema] = []
        for entity_data in entities_data:
            if not isinstance(entity_data, dict):
                continue
            fields = parse_entity_fields(entity_data.get("fields", []))
            entities.append(DBEntitySchema(
                name=entity_data.get("name", ""), fields=fields,
            ))
        return DBSchema(entities=entities)

    def _build_executor_schemas(self, composition: Dict[str, Any]) -> Dict[str, Any]:
        """Build executor schemas from composition blocks (legacy)."""
        schemas: Dict[str, Any] = {}
        blocks = composition.get("blocks", [])
        for block in blocks:
            exec_type = BLOCK_EXECUTOR_MAP.get(block)
            if exec_type and exec_type not in schemas:
                schemas[exec_type] = {
                    "required": [], "optional": [], "rate_limits": {},
                }
        if "database" not in schemas:
            schemas["database"] = {
                "required": ["operation"],
                "denied_operations": ["drop", "truncate"],
                "rate_limits": {"delete": 20, "update": 50},
            }
        return schemas

    def _build_rules(self, risk: Dict[str, Any]) -> List[BusinessRuleDef]:
        """Build business rules from risk assessment (legacy)."""
        rules: List[BusinessRuleDef] = []
        sensitivity = risk.get("data_sensitivity", "medium")

        if sensitivity in ("high", "critical"):
            rules.append(BusinessRuleDef(
                rule_id="bulk_delete_block",
                name="Block bulk delete without confirmation",
                description=f"Data sensitivity is {sensitivity}",
                executor_type="database",
                condition="operation == 'delete' and record_count > 1",
                action="require_confirmation",
                severity="block",
            ))

        if risk.get("audit_trail"):
            rules.append(BusinessRuleDef(
                rule_id="audit_all_actions",
                name="Audit all actions",
                description="Risk assessment requires full audit trail",
                executor_type="*",
                condition="always",
                action="log_audit",
                severity="info",
            ))

        compliance = risk.get("compliance", [])
        if compliance:
            rules.append(BusinessRuleDef(
                rule_id="compliance_check",
                name=f"Compliance: {', '.join(compliance)}",
                description=f"Must comply with {', '.join(compliance)}",
                executor_type="*",
                condition="always",
                action="validate_compliance",
                severity="warning",
            ))

        return rules

    def _build_actions(
        self, niche_name: str, features: Dict[str, Any],
    ) -> List[ActionTemplateDef]:
        """Build action templates from niche features (legacy)."""
        actions: List[ActionTemplateDef] = []
        for feature in features.get("core", []):
            if not isinstance(feature, str):
                continue
            words = re.findall(r'\w+', feature.lower())[:5]
            action_id = f"{niche_name}_{'_'.join(words)}"
            actions.append(ActionTemplateDef(
                template_id=action_id,
                name=feature[:60],
                description=feature,
                executor_type="database",
                safety_category="moderate",
            ))
        return actions

    def _build_monitor_hooks(
        self, workflow: Dict[str, Any], domain: str,
    ) -> List[MonitorHook]:
        """Build SNA monitor hooks from workflow triggers (legacy)."""
        hooks: List[MonitorHook] = []
        triggers = workflow.get("triggers", [])
        for trigger in triggers:
            if not isinstance(trigger, str):
                continue
            hook = self._parse_trigger(trigger, domain)
            if hook is not None:
                hooks.append(hook)
        return hooks

    def _parse_trigger(
        self, trigger: str, domain: str,
    ) -> Optional[MonitorHook]:
        """Parse a single trigger string into a MonitorHook (legacy)."""
        parts = trigger.split(":", 1)
        trigger_id = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else ""

        monitor_id = map_trigger_to_monitor(trigger_id, domain)
        if monitor_id is None:
            monitor_id = trigger_id

        weight = determine_monitor_weight(trigger_id)
        channel = determine_notification_channel(description)

        return MonitorHook(
            monitor_id=monitor_id,
            weight=weight,
            enabled=True,
            params={"trigger_source": trigger_id, "description": description},
            notification_channel=channel,
        )
