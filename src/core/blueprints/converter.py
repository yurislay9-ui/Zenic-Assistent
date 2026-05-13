"""
Zenic-Agents Asistente - Niche-to-Blueprint Converter (Phase 5)

Converts existing Niche YAML templates into certified Blueprints.
Bridges the gap between the legacy template system and the new
Blueprint certification framework.

Conversion mapping:
  niche.name → metadata.name
  niche.domain → metadata.domain
  entities → db_schema.entities
  workflow.triggers → monitor_hooks
  features → action templates
  risk_assessment → business rules + executor constraints
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from .types import (
    ActionTemplateDef, BlueprintMetadataV2, BlueprintTier,
    BusinessRuleDef, DBEntitySchema, DBFieldSchema,
    DBSchema, MonitorHook,
)
from .schema import CertifiedBlueprint
from .convert_parts import (
    BLOCK_EXECUTOR_MAP, parse_entity_fields,
    map_trigger_to_monitor, determine_monitor_weight,
    determine_notification_channel,
)

logger = logging.getLogger(__name__)

# Try YAML
try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

# Risk sensitivity → tier
_SENSITIVITY_TIER_MAP: Dict[str, BlueprintTier] = {
    "low": BlueprintTier.FREE,
    "medium": BlueprintTier.FREE,
    "high": BlueprintTier.PRO,
    "critical": BlueprintTier.ENTERPRISE,
}


# ──────────────────────────────────────────────────────────────
#  NICHE-TO-BLUEPRINT CONVERTER
# ──────────────────────────────────────────────────────────────

class NicheConverter:
    """Converts Niche YAML templates into CertifiedBlueprint objects.

    Usage:
        converter = NicheConverter()
        bp = converter.convert_file("src/templates/niches/retail/inventory_retail.yaml")
        # Or batch convert:
        bps = converter.convert_directory("src/templates/niches/retail/")
    """

    def convert_file(self, filepath: str) -> Optional[CertifiedBlueprint]:
        """Convert a single Niche YAML file to a CertifiedBlueprint."""
        if not _HAS_YAML:
            logger.error("NicheConverter: PyYAML required for conversion")
            return None

        if not os.path.isfile(filepath):
            logger.error("NicheConverter: File not found: %s", filepath)
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = _yaml.safe_load(f)
        except Exception as e:
            logger.error("NicheConverter: Failed to load %s: %s", filepath, e)
            return None

        if not isinstance(data, dict):
            logger.error("NicheConverter: Invalid YAML structure in %s", filepath)
            return None

        return self.convert_dict(data)

    def convert_directory(self, dirpath: str) -> List[CertifiedBlueprint]:
        """Convert all Niche YAML files in a directory."""
        results: List[CertifiedBlueprint] = []

        if not os.path.isdir(dirpath):
            logger.warning("NicheConverter: Directory not found: %s", dirpath)
            return results

        for filename in sorted(os.listdir(dirpath)):
            if not filename.endswith((".yaml", ".yml")):
                continue
            filepath = os.path.join(dirpath, filename)
            bp = self.convert_file(filepath)
            if bp is not None:
                results.append(bp)

        logger.info(
            "NicheConverter: Converted %d niches from %s",
            len(results), dirpath,
        )
        return results

    def convert_all_niches(self, niches_root: str = "") -> List[CertifiedBlueprint]:
        """Convert all niche directories under the niches root."""
        if not niches_root:
            niches_root = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__),
                ))),
                "templates", "niches",
            )

        results: List[CertifiedBlueprint] = []

        if not os.path.isdir(niches_root):
            logger.warning("NicheConverter: Niches root not found: %s", niches_root)
            return results

        for domain_dir in sorted(os.listdir(niches_root)):
            domain_path = os.path.join(niches_root, domain_dir)
            if not os.path.isdir(domain_path):
                continue
            bps = self.convert_directory(domain_path)
            results.extend(bps)

        logger.info("NicheConverter: Converted %d total niches", len(results))
        return results

    def convert_dict(self, data: Dict[str, Any]) -> Optional[CertifiedBlueprint]:
        """Convert a Niche YAML dict to a CertifiedBlueprint."""
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

    # ── Metadata Builder ───────────────────────────────────

    def _build_metadata(
        self, niche: Dict[str, Any], data: Dict[str, Any],
    ) -> BlueprintMetadataV2:
        """Build Blueprint metadata from Niche YAML."""
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

    # ── DB Schema Builder ──────────────────────────────────

    def _build_db_schema(self, entities_data: List[Any]) -> DBSchema:
        """Build DB schema from Niche entities."""
        entities: List[DBEntitySchema] = []
        for entity_data in entities_data:
            if not isinstance(entity_data, dict):
                continue
            fields = parse_entity_fields(entity_data.get("fields", []))
            entities.append(DBEntitySchema(
                name=entity_data.get("name", ""), fields=fields,
            ))
        return DBSchema(entities=entities)

    # ── Executor Schema Builder ────────────────────────────

    def _build_executor_schemas(self, composition: Dict[str, Any]) -> Dict[str, Any]:
        """Build executor schemas from composition blocks."""
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

    # ── Rules Builder ──────────────────────────────────────

    def _build_rules(self, risk: Dict[str, Any]) -> List[BusinessRuleDef]:
        """Build business rules from risk assessment."""
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

    # ── Actions Builder ────────────────────────────────────

    def _build_actions(
        self, niche_name: str, features: Dict[str, Any],
    ) -> List[ActionTemplateDef]:
        """Build action templates from niche features."""
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

    # ── Monitor Hooks Builder ──────────────────────────────

    def _build_monitor_hooks(
        self, workflow: Dict[str, Any], domain: str,
    ) -> List[MonitorHook]:
        """Build SNA monitor hooks from workflow triggers."""
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
        """Parse a single trigger string into a MonitorHook."""
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
