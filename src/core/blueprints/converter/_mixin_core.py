"""Core logic for converter."""

from __future__ import annotations
import logging
import re
from typing import Any, Dict, List, Optional

from ..types import BlueprintTier, BlueprintMetadataV2, DBSchema, DBEntitySchema, DBFieldSchema, BusinessRuleDef, ActionTemplateDef, MonitorHook
from ..convert_parts import BLOCK_EXECUTOR_MAP
from ..schema import CertifiedBlueprint
from ._types import _SENSITIVITY_TIER_MAP
from ._mixin_legacy import NicheConverterLegacyMixin

logger = logging.getLogger(__name__)

class NicheConverter(NicheConverterLegacyMixin):
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
