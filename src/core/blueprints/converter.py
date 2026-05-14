"""
Zenic-Agents Asistente - Niche-to-Blueprint Converter (Phase 5 → Phase 6)

Converts NicheDefinitions from the compiled Rust catalog into certified
Blueprints. This replaces the old YAML-file-based conversion with a
dynamic, Rust-compiled catalog system.

Phase 6 Architecture:
  - Niches are compiled into Rust (no YAML files on disk)
  - User uploads documents → agent creates YAML template dynamically
  - Agent asks user for missing data interactively
  - Completed template → CertifiedBlueprint via certifier

Conversion mapping:
  NicheDefinition.niche_id → metadata.name
  NicheDefinition.domain → metadata.domain
  NicheDefinition.compliance → business rules
  NicheDefinition.data_sensitivity → tier + risk rules
  template sections → db_schema, monitor_hooks, actions
"""

from __future__ import annotations

import logging
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

# Risk sensitivity → tier
_SENSITIVITY_TIER_MAP: Dict[str, BlueprintTier] = {
    "low": BlueprintTier.FREE,
    "medium": BlueprintTier.FREE,
    "high": BlueprintTier.PRO,
    "critical": BlueprintTier.ENTERPRISE,
}


# ──────────────────────────────────────────────────────────────
#  NICHE-TO-BLUEPRINT CONVERTER (Rust Catalog Based)
# ──────────────────────────────────────────────────────────────

class NicheConverter:
    """Converts NicheDefinitions from the Rust catalog into CertifiedBlueprint objects.

    Phase 6: Uses the compiled Rust catalog instead of YAML files.
    The catalog is embedded in the _zenic_native Rust module with
    24 niches compiled at build time.

    Usage:
        converter = NicheConverter()
        # Convert from Rust catalog by niche_id:
        bp = converter.convert_from_catalog("telemedicine")
        # Convert all niches in catalog:
        bps = converter.convert_all_from_catalog()
        # Legacy dict-based conversion still supported:
        bp = converter.convert_dict(data)
    """

    def __init__(self) -> None:
        """Initialize the converter, checking for Rust catalog availability."""
        self._catalog_available = False
        try:
            from src.core.niche_rust.bridge import get_bridge
            bridge = get_bridge()
            if bridge is not None:
                self._catalog_available = True
        except ImportError:
            pass

        if not self._catalog_available:
            logger.warning(
                "NicheConverter: Rust catalog not available. "
                "Install _zenic_native with `maturin develop` for full functionality."
            )

    def convert_from_catalog(self, niche_id: str) -> Optional[CertifiedBlueprint]:
        """Convert a single NicheDefinition from the Rust catalog to a CertifiedBlueprint.

        Args:
            niche_id: The niche identifier from the compiled catalog.

        Returns:
            CertifiedBlueprint if niche found, None otherwise.
        """
        niche_data = self._get_niche_from_catalog(niche_id)
        if niche_data is None:
            logger.error("NicheConverter: Niche '%s' not found in catalog", niche_id)
            return None
        return self._convert_niche_definition(niche_data)

    def convert_all_from_catalog(self) -> List[CertifiedBlueprint]:
        """Convert all NicheDefinitions from the Rust catalog to CertifiedBlueprints.

        Returns:
            List of CertifiedBlueprint objects for all 24 catalog niches.
        """
        if not self._catalog_available:
            logger.warning("NicheConverter: Rust catalog not available for batch conversion")
            return []

        try:
            from src.core.niche_rust.bridge import get_bridge
            bridge = get_bridge()
            all_niches = bridge.list_niches()
            results: List[CertifiedBlueprint] = []
            for niche in all_niches:
                bp = self._convert_niche_definition(niche)
                if bp is not None:
                    results.append(bp)
            logger.info("NicheConverter: Converted %d niches from Rust catalog", len(results))
            return results
        except Exception as exc:
            logger.error("NicheConverter: Batch conversion failed: %s", exc)
            return []

    def _get_niche_from_catalog(self, niche_id: str) -> Optional[Any]:
        """Get a NicheDefinition from the Rust catalog by niche_id."""
        if not self._catalog_available:
            return None
        try:
            from src.core.niche_rust.bridge import get_bridge
            bridge = get_bridge()
            return bridge.get_niche(niche_id)
        except Exception as exc:
            logger.error("NicheConverter: Catalog lookup failed for '%s': %s", niche_id, exc)
            return None

    def _convert_niche_definition(self, niche: Any) -> Optional[CertifiedBlueprint]:
        """Convert a NicheDefinition object from the Rust catalog to a CertifiedBlueprint.

        Maps the compiled niche data into the Blueprint framework:
        - niche_id → metadata.name
        - domain → metadata.domain
        - data_sensitivity → tier + risk rules
        - compliance → business rules
        - required_documents → monitor hints
        """
        try:
            niche_id = niche.niche_id
            name = niche.name
            domain = niche.domain
            subdomain = niche.subdomain
            description = niche.description
            scale = niche.scale
            sensitivity = niche.data_sensitivity.as_str() if hasattr(niche.data_sensitivity, 'as_str') else str(niche.data_sensitivity)
            compliance = niche.compliance if niche.compliance else []
            tags = niche.tags if niche.tags else []
            required_docs = niche.required_documents if niche.required_documents else []

            # Build metadata
            metadata = BlueprintMetadataV2(
                name=niche_id,
                version="1.0.0",
                domain=domain,
                subdomain=subdomain,
                description=description,
                author="zenic-agents",
                tier=_SENSITIVITY_TIER_MAP.get(sensitivity, BlueprintTier.FREE),
                tags=tags + [domain],
                scale=scale,
            )

            # Build DB schema from template sections
            db_schema = self._build_db_schema_from_sections(niche)

            # Build executor schemas
            executor_schemas = self._build_executor_schemas_from_niche(niche)

            # Build rules from sensitivity + compliance
            rules = self._build_rules_from_niche(sensitivity, compliance)

            # Build actions from required_documents
            actions = self._build_actions_from_niche(niche_id, required_docs)

            # Build monitor hooks from compliance requirements
            monitor_hooks = self._build_monitor_hooks_from_niche(compliance, domain)

            return CertifiedBlueprint(
                metadata=metadata,
                db_schema=db_schema,
                executor_schemas=executor_schemas,
                rules=rules,
                actions=actions,
                monitor_hooks=monitor_hooks,
            )
        except Exception as exc:
            logger.error("NicheConverter: Failed to convert niche: %s", exc)
            return None

    # ── Section-based DB Schema Builder ──────────────────────

    def _build_db_schema_from_sections(self, niche: Any) -> DBSchema:
        """Build DB schema from the NicheDefinition's template sections."""
        entities: List[DBEntitySchema] = []
        try:
            section_count = niche.section_count()
            for i in range(section_count):
                section_ids = niche.section_ids()
                if i < len(section_ids):
                    section = niche.get_section(section_ids[i])
                    if section is not None:
                        fields: List[DBFieldSchema] = []
                        for field_name in section.field_names():
                            field = section.get_field(field_name)
                            if field is not None:
                                fields.append(DBFieldSchema(
                                    name=field.name,
                                    col_type=self._field_type_to_col_type(field.field_type.as_str() if hasattr(field.field_type, 'as_str') else str(field.field_type)),
                                ))
                        entities.append(DBEntitySchema(
                            name=section_ids[i],
                            fields=fields,
                        ))
        except Exception as exc:
            logger.warning("NicheConverter: Could not extract sections: %s", exc)

        return DBSchema(entities=entities)

    @staticmethod
    def _field_type_to_col_type(field_type: str) -> str:
        """Map a TemplateFieldType to a database column type."""
        mapping = {
            "text": "TEXT",
            "number": "REAL",
            "boolean": "INTEGER",
            "date": "TEXT",
            "datetime": "TEXT",
            "email": "TEXT",
            "url": "TEXT",
            "phone": "TEXT",
            "currency": "REAL",
            "percentage": "REAL",
            "json": "TEXT",
            "enum": "TEXT",
            "reference": "TEXT",
            "file": "TEXT",
        }
        return mapping.get(field_type, "TEXT")

    # ── Executor Schema Builder ──────────────────────────────

    @staticmethod
    def _build_executor_schemas_from_niche(niche: Any) -> Dict[str, Any]:
        """Build executor schemas from niche section IDs."""
        schemas: Dict[str, Any] = {}
        try:
            for section_id in niche.section_ids():
                exec_type = BLOCK_EXECUTOR_MAP.get(section_id)
                if exec_type and exec_type not in schemas:
                    schemas[exec_type] = {
                        "required": [], "optional": [], "rate_limits": {},
                    }
        except Exception:
            pass

        if "database" not in schemas:
            schemas["database"] = {
                "required": ["operation"],
                "denied_operations": ["drop", "truncate"],
                "rate_limits": {"delete": 20, "update": 50},
            }
        return schemas

    # ── Rules Builder ──────────────────────────────────────

    @staticmethod
    def _build_rules_from_niche(
        sensitivity: str, compliance: List[str],
    ) -> List[BusinessRuleDef]:
        """Build business rules from sensitivity and compliance data."""
        rules: List[BusinessRuleDef] = []

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

        if sensitivity in ("high", "critical"):
            rules.append(BusinessRuleDef(
                rule_id="audit_all_actions",
                name="Audit all actions",
                description=f"Data sensitivity {sensitivity} requires full audit trail",
                executor_type="*",
                condition="always",
                action="log_audit",
                severity="info",
            ))

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

    @staticmethod
    def _build_actions_from_niche(
        niche_name: str, required_docs: List[str],
    ) -> List[ActionTemplateDef]:
        """Build action templates from niche required documents."""
        actions: List[ActionTemplateDef] = []
        for doc in required_docs:
            if not isinstance(doc, str):
                continue
            words = re.findall(r'\w+', doc.lower())[:5]
            action_id = f"{niche_name}_upload_{'_'.join(words)}"
            actions.append(ActionTemplateDef(
                template_id=action_id,
                name=f"Upload {doc[:50]}",
                description=f"Upload and process {doc} for {niche_name}",
                executor_type="database",
                safety_category="moderate",
            ))
        return actions

    # ── Monitor Hooks Builder ──────────────────────────────

    @staticmethod
    def _build_monitor_hooks_from_niche(
        compliance: List[str], domain: str,
    ) -> List[MonitorHook]:
        """Build SNA monitor hooks from compliance requirements."""
        hooks: List[MonitorHook] = []
        for standard in compliance:
            if not isinstance(standard, str):
                continue
            monitor_id = f"compliance_{standard.lower().replace(' ', '_').replace('.', '')}"
            hooks.append(MonitorHook(
                monitor_id=monitor_id,
                weight=0.9,
                enabled=True,
                params={"compliance_standard": standard, "domain": domain},
                notification_channel="alert",
            ))
        return hooks

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
