"""
Zenic-Agents Asistente - Blueprints Certificados (Phase 5)

From YAML templates to certified, composable Blueprints.

Architecture:
  BlueprintRegistry (facade + singleton)
  ├── BlueprintLoaderV2 (load from YAML/JSON/dict)
  ├── NicheConverter (Niche YAML → CertifiedBlueprint)
  ├── BlueprintComposer (compose multiple Blueprints)
  ├── BlueprintValidatorV2 (schema + compatibility validation)
  ├── BlueprintCertifier (ECDSA signing + verification)
  ├── OnboardingEngine (guided setup flow)
  └── BlueprintSDK (partner API + revenue share)

Usage:
    from src.core.blueprints import get_blueprint_registry

    registry = get_blueprint_registry()
    registry.load_from_niches()

    # Get a Blueprint
    bp = registry.get("inventory_retail")

    # Compose for a tenant
    result = registry.compose_for_tenant(
        tenant_id="acme",
        blueprint_names=["inventory_retail", "accounting"],
    )
    if result.success:
        active_bp = result.blueprint
"""

# ── Types ─────────────────────────────────────────────────────
from .types import (
    # Enums
    BlueprintStatus,
    BlueprintTier,
    FieldType,
    ConflictStrategy,
    OnboardingStepType,
    # Dataclasses
    DBFieldSchema,
    DBEntitySchema,
    DBSchema,
    MonitorHook,
    BusinessRuleDef,
    ActionTemplateDef,
    BlueprintSignature,
    BlueprintCompatibility,
    BlueprintMetadataV2,
    OnboardingStep,
    OnboardingSession,
    PartnerInfo,
    BlueprintStats,
)

# ── Schema ────────────────────────────────────────────────────
from .schema import CertifiedBlueprint

# ── Validator ─────────────────────────────────────────────────
from .validator import BlueprintValidatorV2, ValidationResult

# ── Certifier ─────────────────────────────────────────────────
from .certifier import (
    CertifierKeyPair,
    BlueprintCertifier,
    get_default_certifier,
    certify_blueprint,
    verify_blueprint,
)

# ── Loader ────────────────────────────────────────────────────
from .loader import BlueprintLoaderV2

# ── Composer ──────────────────────────────────────────────────
from .composer import BlueprintComposer, CompositionResult

# ── Converter ─────────────────────────────────────────────────
from .converter import NicheConverter

# ── Onboarding ────────────────────────────────────────────────
from .onboarding import OnboardingEngine

# ── SDK ───────────────────────────────────────────────────────
from .sdk import BlueprintSDK, BlueprintBuilder

# ── Partner Registry ──────────────────────────────────────────
from .partner_registry import PartnerRegistry

# ── Registry ──────────────────────────────────────────────────
from .registry import (
    BlueprintRegistry,
    get_blueprint_registry,
    reset_blueprint_registry,
)

__all__ = [
    # Types
    "BlueprintStatus", "BlueprintTier", "FieldType",
    "ConflictStrategy", "OnboardingStepType",
    "DBFieldSchema", "DBEntitySchema", "DBSchema",
    "MonitorHook", "BusinessRuleDef", "ActionTemplateDef",
    "BlueprintSignature", "BlueprintCompatibility",
    "BlueprintMetadataV2",
    "OnboardingStep", "OnboardingSession",
    "PartnerInfo", "BlueprintStats",
    # Schema
    "CertifiedBlueprint",
    # Validator
    "BlueprintValidatorV2", "ValidationResult",
    # Certifier
    "CertifierKeyPair", "BlueprintCertifier",
    "get_default_certifier", "certify_blueprint", "verify_blueprint",
    # Loader
    "BlueprintLoaderV2",
    # Composer
    "BlueprintComposer", "CompositionResult",
    # Converter
    "NicheConverter",
    # Onboarding
    "OnboardingEngine",
    # SDK
    "BlueprintSDK", "BlueprintBuilder", "PartnerRegistry",
    # Registry
    "BlueprintRegistry", "get_blueprint_registry",
    "reset_blueprint_registry",
]
