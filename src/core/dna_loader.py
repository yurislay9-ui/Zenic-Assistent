"""
ZENIC-AGENTS - DNALoader — Facade

Cargador de Plantillas Maestras de ADN Técnico.

This module is a thin facade; all logic lives in dna_loader_parts/.

Phase 5 integration: DNALoader now delegates Blueprint-aware
operations to the Blueprint Registry when available. Domain rules
and validation gates can also come from active Blueprints.
"""

from .dna_loader_parts import *  # noqa: F401,F403
from .dna_loader_parts import (
    DNALoader, LogicModule, DomainRule, ValidationGate,
    GlossaryEntry, DNA_ROOT, YAML_AVAILABLE, get_dna_loader,
)

__all__ = [
    "DNALoader",
    "LogicModule",
    "DomainRule",
    "ValidationGate",
    "GlossaryEntry",
    "DNA_ROOT",
    "YAML_AVAILABLE",
    "get_dna_loader",
]


def get_domain_rules_from_blueprint(
    domain: str,
) -> list:
    """Get domain rules from active Blueprints (Phase 5).

    Queries the Blueprint Registry for Blueprints matching the
    given domain and returns their business rules as DomainRule-
    compatible objects. Falls back to DNALoader if no Blueprints.

    Returns:
        List of DomainRule objects from Blueprints or DNALoader.
    """
    try:
        from .blueprints import get_blueprint_registry
        registry = get_blueprint_registry()
        bps = registry.get_by_domain(domain)
        if bps:
            rules = []
            for bp in bps:
                for rule in bp.rules:
                    rules.append(DomainRule(
                        name=rule.rule_id,
                        display_name=rule.name,
                        description=rule.description,
                        mandatory_logic=[rule.condition],
                        compliance_requirements=(
                            [rule.action] if rule.action else []
                        ),
                    ))
            return rules
    except Exception:
        pass

    # Fallback to DNALoader
    loader = get_dna_loader()
    if not loader._loaded:
        loader.load_all()
    return list(loader._domain_rules.values())
