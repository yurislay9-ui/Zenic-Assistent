"""
Zenic-Agents Asistente - Blueprint Registry (Phase 5)

Central registry for all active Blueprints.
Manages:
  - Blueprint lookup by name, domain, tier
  - Active Blueprint composition per tenant
  - Blueprint caching and lifecycle
  - Integration with SNA, ActionDispatcher, and DNALoader
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from .types import (
    BlueprintStats, BlueprintStatus, BlueprintTier,
)
from .schema import CertifiedBlueprint
from .loader import BlueprintLoaderV2
from .converter import NicheConverter
from .composer import BlueprintComposer, CompositionResult
from .validator import BlueprintValidatorV2

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  BLUEPRINT REGISTRY
# ──────────────────────────────────────────────────────────────

class BlueprintRegistry:
    """Central registry for CertifiedBlueprints.

    Manages the lifecycle of Blueprints: loading, caching,
    composition per tenant, and integration with other subsystems.

    Usage:
        registry = BlueprintRegistry()

        # Load from directories
        registry.load_from_directory("blueprints/")

        # Convert niches
        registry.load_from_niches("src/templates/niches/")

        # Get a Blueprint
        bp = registry.get("retail_inventory")

        # Compose for a tenant
        composed = registry.compose_for_tenant(
            tenant_id="acme",
            blueprint_names=["retail_inventory", "billing"],
        )

        # Get tenant's active Blueprint
        active = registry.get_tenant_blueprint("acme")
    """

    def __init__(
        self,
        loader: Optional[BlueprintLoaderV2] = None,
        composer: Optional[BlueprintComposer] = None,
        validator: Optional[BlueprintValidatorV2] = None,
    ) -> None:
        self._loader = loader or BlueprintLoaderV2()
        self._composer = composer or BlueprintComposer()
        self._validator = validator or BlueprintValidatorV2()

        self._blueprints: Dict[str, CertifiedBlueprint] = {}
        self._tenant_blueprints: Dict[str, CertifiedBlueprint] = {}
        self._stats: Dict[str, BlueprintStats] = {}

        self._lock = threading.RLock()

    # ── Loading ────────────────────────────────────────────

    def load_from_directory(self, dirpath: str, verify: bool = True) -> int:
        """Load Blueprints from a directory of YAML/JSON files."""
        bps = self._loader.load_directory(dirpath, verify=verify)
        with self._lock:
            for bp in bps:
                self._blueprints[bp.metadata.name] = bp
        return len(bps)

    def load_from_niches(self, niches_root: str = "") -> int:
        """Convert and load niches from the compiled Rust catalog as Blueprints.

        Phase 6: Niches are now compiled into Rust, not loaded from YAML files.
        The niches_root parameter is kept for API compatibility but is no longer used.
        All niche definitions come from the _zenic_native Rust catalog.
        """
        converter = NicheConverter()
        bps = converter.convert_all_from_catalog()
        with self._lock:
            for bp in bps:
                self._blueprints[bp.metadata.name] = bp
        return len(bps)

    def register(self, blueprint: CertifiedBlueprint) -> None:
        """Register a Blueprint manually."""
        with self._lock:
            self._blueprints[blueprint.metadata.name] = blueprint
        logger.info(
            "BlueprintRegistry: Registered '%s' v%s (%s)",
            blueprint.metadata.name,
            blueprint.metadata.version,
            blueprint.metadata.domain,
        )

    def unregister(self, name: str) -> bool:
        """Unregister a Blueprint."""
        with self._lock:
            if name in self._blueprints:
                del self._blueprints[name]
                return True
            return False

    # ── Lookup ─────────────────────────────────────────────

    def get(self, name: str) -> Optional[CertifiedBlueprint]:
        """Get a Blueprint by name."""
        with self._lock:
            return self._blueprints.get(name)

    def get_by_domain(self, domain: str) -> List[CertifiedBlueprint]:
        """Get all Blueprints for a domain."""
        with self._lock:
            return [
                bp for bp in self._blueprints.values()
                if bp.metadata.domain == domain
            ]

    def get_by_tier(self, tier: BlueprintTier) -> List[CertifiedBlueprint]:
        """Get all Blueprints for a tier."""
        with self._lock:
            return [
                bp for bp in self._blueprints.values()
                if bp.metadata.tier == tier
            ]

    def get_certified(self) -> List[CertifiedBlueprint]:
        """Get all certified Blueprints."""
        with self._lock:
            return [bp for bp in self._blueprints.values() if bp.is_certified]

    def list_all(self) -> List[str]:
        """List all registered Blueprint names."""
        with self._lock:
            return list(self._blueprints.keys())

    def list_domains(self) -> List[str]:
        """List all available domains."""
        with self._lock:
            domains = set()
            for bp in self._blueprints.values():
                if bp.metadata.domain:
                    domains.add(bp.metadata.domain)
            return sorted(domains)

    def search(
        self, query: str, domain: str = "", tier: str = "",
    ) -> List[CertifiedBlueprint]:
        """Search Blueprints by name, description, or tags."""
        query_lower = query.lower()
        with self._lock:
            results = []
            for bp in self._blueprints.values():
                if domain and bp.metadata.domain != domain:
                    continue
                if tier and bp.metadata.tier.value != tier:
                    continue
                # Search in name, description, tags
                searchable = (
                    bp.metadata.name.lower()
                    + " " + bp.metadata.description.lower()
                    + " " + " ".join(bp.metadata.tags).lower()
                    + " " + bp.metadata.domain.lower()
                    + " " + bp.metadata.subdomain.lower()
                )
                if query_lower in searchable:
                    results.append(bp)
            return results

    # ── Tenant Composition ─────────────────────────────────

    def compose_for_tenant(
        self,
        tenant_id: str,
        blueprint_names: List[str],
        certify: bool = False,
    ) -> CompositionResult:
        """Compose multiple Blueprints for a specific tenant.

        The composed Blueprint is cached per tenant.
        """
        bps = []
        for name in blueprint_names:
            bp = self._blueprints.get(name)
            if bp is None:
                logger.warning(
                    "BlueprintRegistry: Blueprint '%s' not found for tenant %s",
                    name, tenant_id,
                )
                continue
            bps.append(bp)

        if not bps:
            result = CompositionResult()
            result.warnings.append("No valid Blueprints to compose")
            return result

        result = self._composer.compose(
            bps,
            composed_name=f"tenant_{tenant_id}",
        )

        if result.blueprint is not None:
            with self._lock:
                self._tenant_blueprints[tenant_id] = result.blueprint

            # Update stats
            for name in blueprint_names:
                if name not in self._stats:
                    self._stats[name] = BlueprintStats()
                self._stats[name].installations += 1

        return result

    def get_tenant_blueprint(
        self, tenant_id: str,
    ) -> Optional[CertifiedBlueprint]:
        """Get the composed Blueprint for a tenant."""
        with self._lock:
            return self._tenant_blueprints.get(tenant_id)

    def remove_tenant_blueprint(self, tenant_id: str) -> bool:
        """Remove a tenant's composed Blueprint."""
        with self._lock:
            if tenant_id in self._tenant_blueprints:
                del self._tenant_blueprints[tenant_id]
                return True
            return False

    # ── Statistics ─────────────────────────────────────────

    def get_stats(self, name: str) -> Optional[BlueprintStats]:
        """Get statistics for a specific Blueprint."""
        return self._stats.get(name)

    @property
    def overview(self) -> Dict[str, Any]:
        """Get registry overview statistics."""
        with self._lock:
            return {
                "total_blueprints": len(self._blueprints),
                "total_certified": len(self.get_certified()),
                "total_domains": len(self.list_domains()),
                "active_tenants": len(self._tenant_blueprints),
                "domains": self.list_domains(),
            }

    @property
    def detailed_stats(self) -> Dict[str, Any]:
        """Get detailed registry statistics."""
        with self._lock:
            bp_stats = {}
            for name, bp in self._blueprints.items():
                bp_stats[name] = bp.stats

            return {
                "overview": self.overview,
                "blueprints": bp_stats,
                "tenants": {
                    tid: bp.metadata.name
                    for tid, bp in self._tenant_blueprints.items()
                },
            }


# ──────────────────────────────────────────────────────────────
#  GLOBAL INSTANCE
# ──────────────────────────────────────────────────────────────

_default_registry: Optional[BlueprintRegistry] = None
_registry_lock = threading.Lock()


def get_blueprint_registry() -> BlueprintRegistry:
    """Get or create the global BlueprintRegistry singleton."""
    global _default_registry
    if _default_registry is None:
        with _registry_lock:
            if _default_registry is None:
                _default_registry = BlueprintRegistry()
    return _default_registry


def reset_blueprint_registry() -> None:
    """Reset the global registry (for testing)."""
    global _default_registry
    _default_registry = None
