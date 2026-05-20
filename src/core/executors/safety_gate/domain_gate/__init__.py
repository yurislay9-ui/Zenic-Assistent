"""
DomainSafetyGate — Extended safety gate with domain-specific rules and compliance.

Python wrapper for the Rust-compiled zenic-safety crate (Phase D).
Provides 4-layer safety validation:
    1. Base SafetyGate (10 generic rules)
    2. Domain-specific rules (5 per NicheCategory = 35 total)
    3. Compliance validation (HIPAA, PCI-DSS, GDPR, SOX, AML/KYC, COPPA, ISO 27001, SOC 2)
    4. Sensitivity escalation (critical → auto-deny high-risk actions)

INVARIANT: Domain rules can only ESCALATE verdicts, never downgrade.
Compliance failures for critical violations result in DENY.

Python fallback is fully deterministic — mirrors the Rust logic exactly.
"""

from ._helpers import (
    ComplianceResult,
    DomainSafetyCheckResult,
    _COMPLIANCE_CHECKERS,
    _COMPILED_DOMAIN_RULES,
    _PYTHON_DOMAIN_RULES,
    _VERDICT_SEVERITY,
    _check_compliance_aml_kyc,
    _check_compliance_coppa,
    _check_compliance_gdpr,
    _check_compliance_hipaa,
    _check_compliance_iso_27001,
    _check_compliance_pci_dss,
    _check_compliance_soc2,
    _check_compliance_sox,
    _escalate_verdict,
    _sensitivity_escalate,
)
from ._core import (
    DomainSafetyGate,
    get_default_domain_safety_gate,
)

__all__ = [
    "ComplianceResult",
    "DomainSafetyCheckResult",
    "DomainSafetyGate",
    "get_default_domain_safety_gate",
]
