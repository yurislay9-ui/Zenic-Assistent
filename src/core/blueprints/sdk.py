"""
Zenic-Agents Asistente - Blueprint SDK for Partners (Phase 5)

API for partners to create, validate, certify, and publish
custom Blueprints. Includes fluent builder, certification
workflow, and revenue tracking.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .types import (
    ActionTemplateDef, BlueprintMetadataV2, BlueprintTier,
    BusinessRuleDef, DBEntitySchema,
    DBSchema, MonitorHook,
)
from .schema import CertifiedBlueprint
from .validator import BlueprintValidatorV2, ValidationResult
from .certifier import BlueprintCertifier, certify_blueprint
from .partner_registry import PartnerRegistry

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  BLUEPRINT SDK
# ──────────────────────────────────────────────────────────────

class BlueprintSDK:
    """Public API for partners to create and manage Blueprints.

    Usage:
        sdk = BlueprintSDK()
        builder = sdk.create_blueprint("my_plugin", domain="retail")
        builder.add_entity(...)
        blueprint = builder.build()
        result = sdk.validate(blueprint)
        sdk.submit_for_certification(blueprint, partner_id="partner_123")
        sdk.publish(blueprint)
    """

    def __init__(
        self,
        certifier: Optional[BlueprintCertifier] = None,
        partner_registry: Optional[PartnerRegistry] = None,
    ) -> None:
        self._certifier = certifier or BlueprintCertifier()
        self._registry = partner_registry or PartnerRegistry()
        self._validator = BlueprintValidatorV2()
        self._published: Dict[str, CertifiedBlueprint] = {}
        self._submission_hooks: List[Callable] = []

    # ── Blueprint Creation ─────────────────────────────────

    def create_blueprint(
        self, name: str, domain: str = "", subdomain: str = "",
        description: str = "", author: str = "", tier: str = "partner",
    ) -> "BlueprintBuilder":
        """Create a new Blueprint using the builder pattern."""
        return BlueprintBuilder(
            sdk=self, name=name, domain=domain, subdomain=subdomain,
            description=description, author=author, tier=tier,
        )

    # ── Validation ─────────────────────────────────────────

    def validate(self, blueprint: CertifiedBlueprint) -> ValidationResult:
        """Validate a Blueprint before certification."""
        return self._validator.validate(blueprint)

    # ── Certification ──────────────────────────────────────

    def submit_for_certification(
        self, blueprint: CertifiedBlueprint, partner_id: str = "",
    ) -> Dict[str, Any]:
        """Submit a Blueprint for certification."""
        validation = self._validator.validate(blueprint)
        if not validation.is_valid:
            return {
                "certified": False,
                "errors": validation.errors,
                "warnings": validation.warnings,
            }

        if partner_id and not self._registry.is_certified_partner(partner_id):
            return {
                "certified": False,
                "errors": [f"Partner '{partner_id}' is not certified"],
                "warnings": [],
            }

        try:
            signature = certify_blueprint(blueprint)
        except Exception as e:
            return {
                "certified": False,
                "errors": [f"Signing failed: {e}"],
                "warnings": [],
            }

        if partner_id:
            blueprint.metadata.tier = BlueprintTier.PARTNER
            blueprint.metadata.author = partner_id

        for hook in self._submission_hooks:
            try:
                hook(blueprint, partner_id)
            except Exception as e:
                logger.warning("BlueprintSDK: Submission hook error: %s", e)

        return {
            "certified": True,
            "certificate_id": signature.certificate_id,
            "algorithm": signature.algorithm,
            "signed_at": signature.signed_at,
            "warnings": validation.warnings,
        }

    # ── Publication ────────────────────────────────────────

    def publish(self, blueprint: CertifiedBlueprint) -> bool:
        """Publish a certified Blueprint for distribution."""
        if not blueprint.is_certified:
            logger.warning(
                "BlueprintSDK: Cannot publish uncertified Blueprint '%s'",
                blueprint.metadata.name,
            )
            return False
        self._published[blueprint.metadata.name] = blueprint
        logger.info(
            "BlueprintSDK: Published '%s' v%s",
            blueprint.metadata.name, blueprint.metadata.version,
        )
        return True

    def unpublish(self, name: str) -> bool:
        """Remove a published Blueprint."""
        if name in self._published:
            del self._published[name]
            return True
        return False

    def get_published(self, name: str) -> Optional[CertifiedBlueprint]:
        """Get a published Blueprint by name."""
        return self._published.get(name)

    def list_published(self, domain: str = "") -> List[Dict[str, Any]]:
        """List all published Blueprints."""
        results = []
        for bp in self._published.values():
            if domain and bp.metadata.domain != domain:
                continue
            results.append(bp.stats)
        return results

    # ── Revenue Tracking ───────────────────────────────────

    def record_install(self, blueprint_name: str, tenant_id: str) -> None:
        """Record a Blueprint installation for revenue tracking."""
        bp = self._published.get(blueprint_name)
        if bp is None:
            return
        partner_id = bp.metadata.author
        info = self._registry.get_partner(partner_id)
        if info and info.revenue_share_pct > 0:
            share_cents = int(info.revenue_share_pct * 100)  # Store as basis points (1/100 of %)
            self._registry.record_revenue(partner_id, share_cents)

    # ── Partner Management ─────────────────────────────────

    @property
    def partners(self) -> PartnerRegistry:
        """Access the partner registry."""
        return self._registry

    def on_submission(self, callback: Callable) -> None:
        """Register a callback for Blueprint submissions."""
        self._submission_hooks.append(callback)


# ──────────────────────────────────────────────────────────────
#  BLUEPRINT BUILDER (Fluent API)
# ──────────────────────────────────────────────────────────────

class BlueprintBuilder:
    """Fluent builder for creating Blueprints step by step.

    Usage:
        blueprint = (
            BlueprintBuilder(sdk, name="my_plugin", domain="retail")
            .with_description("My custom retail plugin")
            .add_entity(DBEntitySchema(name="Product", fields=[...]))
            .add_monitor(MonitorHook(monitor_id="low_stock", ...))
            .build()
        )
    """

    def __init__(
        self, sdk: BlueprintSDK, name: str, domain: str = "",
        subdomain: str = "", description: str = "",
        author: str = "", tier: str = "partner",
    ) -> None:
        self._sdk = sdk
        self._metadata = BlueprintMetadataV2(
            name=name, domain=domain, subdomain=subdomain,
            description=description, author=author,
            tier=BlueprintTier(tier),
        )
        self._db_schema = DBSchema()
        self._executor_schemas: Dict[str, Any] = {}
        self._rules: List[BusinessRuleDef] = []
        self._actions: List[ActionTemplateDef] = []
        self._monitors: List[MonitorHook] = []

    def with_description(self, description: str) -> "BlueprintBuilder":
        self._metadata.description = description
        return self

    def with_author(self, author: str) -> "BlueprintBuilder":
        self._metadata.author = author
        return self

    def with_tags(self, tags: List[str]) -> "BlueprintBuilder":
        self._metadata.tags = tags
        return self

    def with_scale(self, scale: str) -> "BlueprintBuilder":
        self._metadata.scale = scale
        return self

    def add_entity(self, entity: DBEntitySchema) -> "BlueprintBuilder":
        self._db_schema.entities.append(entity)
        return self

    def add_executor_schema(
        self, executor_type: str, schema: Dict[str, Any],
    ) -> "BlueprintBuilder":
        self._executor_schemas[executor_type] = schema
        return self

    def add_rule(self, rule: BusinessRuleDef) -> "BlueprintBuilder":
        self._rules.append(rule)
        return self

    def add_action(self, action: ActionTemplateDef) -> "BlueprintBuilder":
        self._actions.append(action)
        return self

    def add_monitor(self, monitor: MonitorHook) -> "BlueprintBuilder":
        self._monitors.append(monitor)
        return self

    def validate(self) -> ValidationResult:
        """Validate the Blueprint being built (without building it)."""
        return self._sdk.validate(self._build_internal())

    def build(self) -> CertifiedBlueprint:
        """Build the final CertifiedBlueprint."""
        return self._build_internal()

    def build_and_certify(self) -> Dict[str, Any]:
        """Build and submit for certification in one step."""
        return self._sdk.submit_for_certification(
            self._build_internal(), partner_id=self._metadata.author,
        )

    def _build_internal(self) -> CertifiedBlueprint:
        """Internal build method."""
        return CertifiedBlueprint(
            metadata=self._metadata,
            db_schema=self._db_schema,
            executor_schemas=self._executor_schemas,
            rules=self._rules,
            actions=self._actions,
            monitor_hooks=self._monitors,
        )
