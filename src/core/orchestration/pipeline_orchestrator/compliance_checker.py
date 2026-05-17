"""
Compliance Checker — Compliance verification for pipeline orchestration.

Provides compliance checking against regulatory standards (HIPAA, PCI-DSS,
SOC 2, GDPR, etc.) for pipeline execution, data handling, and
operational procedures.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
No external dependencies beyond Python stdlib.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

__all__ = [
    "ComplianceStandard",
    "ComplianceResult",
    "ComplianceChecker",
]


# ──────────────────────────────────────────────────────────────
#  DATA CONTRACTS
# ──────────────────────────────────────────────────────────────

class ComplianceStandard(str, Enum):
    """Supported compliance standards."""
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    SOC2 = "soc2"
    GDPR = "gdpr"
    SOX = "sox"
    ISO_27001 = "iso_27001"
    NIST = "nist"
    CUSTOM = "custom"


class ComplianceSeverity(str, Enum):
    """Severity of a compliance violation."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ComplianceViolation:
    """
    A single compliance violation.

    Attributes:
        rule_id: The rule that was violated.
        standard: The compliance standard.
        severity: Severity of the violation.
        description: Human-readable description.
        remediation: Suggested remediation steps.
        affected_resource: The resource or step that is non-compliant.
        metadata: Additional metadata.
    """
    rule_id: str
    standard: ComplianceStandard
    severity: ComplianceSeverity = ComplianceSeverity.MEDIUM
    description: str = ""
    remediation: str = ""
    affected_resource: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceResult:
    """
    Result of a compliance check.

    Attributes:
        compliant: Whether the check passed (no violations).
        standard: The compliance standard checked.
        violations: List of violations found.
        warnings: List of non-blocking warnings.
        checked_at: Timestamp when the check was performed.
        duration_ms: Duration of the check in milliseconds.
        metadata: Additional metadata.
    """
    compliant: bool = True
    standard: ComplianceStandard = ComplianceStandard.CUSTOM
    violations: List[ComplianceViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    checked_at: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_critical(self) -> bool:
        """Whether there are any critical violations."""
        return any(v.severity == ComplianceSeverity.CRITICAL for v in self.violations)

    @property
    def has_high(self) -> bool:
        """Whether there are any high-severity violations."""
        return any(v.severity == ComplianceSeverity.HIGH for v in self.violations)

    @property
    def violation_count(self) -> int:
        """Total number of violations."""
        return len(self.violations)

    @property
    def summary(self) -> str:
        """Human-readable summary of the result."""
        if self.compliant:
            return f"COMPLIANT ({self.standard.value})"
        critical = sum(1 for v in self.violations if v.severity == ComplianceSeverity.CRITICAL)
        high = sum(1 for v in self.violations if v.severity == ComplianceSeverity.HIGH)
        medium = sum(1 for v in self.violations if v.severity == ComplianceSeverity.MEDIUM)
        low = sum(1 for v in self.violations if v.severity == ComplianceSeverity.LOW)
        return (
            f"NON-COMPLIANT ({self.standard.value}): "
            f"{critical} critical, {high} high, {medium} medium, {low} low"
        )


# ──────────────────────────────────────────────────────────────
#  RULE DEFINITIONS
# ──────────────────────────────────────────────────────────────

class ComplianceRule:
    """
    A single compliance rule that can be checked.

    Attributes:
        rule_id: Unique identifier for the rule.
        standard: The compliance standard this rule belongs to.
        description: Human-readable description.
        severity: Default severity if the rule is violated.
        check_fn: Callable that returns True if compliant, False otherwise.
    """

    def __init__(
        self,
        rule_id: str,
        standard: ComplianceStandard,
        description: str,
        severity: ComplianceSeverity = ComplianceSeverity.MEDIUM,
        check_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
        remediation: str = "",
    ) -> None:
        self.rule_id = rule_id
        self.standard = standard
        self.description = description
        self.severity = severity
        self.check_fn = check_fn or (lambda _: True)
        self.remediation = remediation

    def check(self, context: Dict[str, Any]) -> Optional[ComplianceViolation]:
        """
        Check this rule against the given context.

        Args:
            context: Dictionary with pipeline/step data to check.

        Returns:
            ComplianceViolation if the rule is violated, None if compliant.
        """
        try:
            is_compliant = self.check_fn(context)
            if not is_compliant:
                return ComplianceViolation(
                    rule_id=self.rule_id,
                    standard=self.standard,
                    severity=self.severity,
                    description=self.description,
                    remediation=self.remediation,
                )
            return None
        except Exception as exc:
            logger.error(
                "ComplianceChecker: Rule '%s' check failed: %s",
                self.rule_id, exc,
            )
            return ComplianceViolation(
                rule_id=self.rule_id,
                standard=self.standard,
                severity=ComplianceSeverity.LOW,
                description=f"Rule check error: {exc}",
                remediation="Fix the rule implementation or context data.",
            )


# ──────────────────────────────────────────────────────────────
#  COMPLIANCE CHECKER
# ──────────────────────────────────────────────────────────────

class ComplianceChecker:
    """
    Compliance verification for pipeline orchestration.

    Supports:
    - Built-in rules for HIPAA, PCI-DSS, SOC2, GDPR, SOX, ISO 27001, NIST
    - Custom rule registration
    - Context-based compliance checking
    - Multi-standard batch checking
    - Compliance audit trail

    Usage::

        checker = ComplianceChecker()
        checker.install_default_rules()

        context = {
            "data_sensitivity": "phi",
            "encryption_enabled": True,
            "audit_logging": True,
            "access_controls": True,
        }

        result = checker.check(ComplianceStandard.HIPAA, context)
        if not result.compliant:
            for v in result.violations:
                print(f"  [{v.severity.value}] {v.rule_id}: {v.description}")

    Thread Safety:
        This class is NOT thread-safe. External synchronization is required.
    """

    def __init__(self) -> None:
        self._rules: Dict[str, ComplianceRule] = {}
        self._rules_by_standard: Dict[ComplianceStandard, List[str]] = {}
        self._audit_trail: List[ComplianceResult] = []

    # ── Rule Management ──────────────────────────────────────

    def add_rule(self, rule: ComplianceRule) -> None:
        """
        Register a compliance rule.

        Args:
            rule: The ComplianceRule to register.
        """
        self._rules[rule.rule_id] = rule
        if rule.standard not in self._rules_by_standard:
            self._rules_by_standard[rule.standard] = []
        self._rules_by_standard[rule.standard].append(rule.rule_id)
        logger.debug(
            "ComplianceChecker: Added rule '%s' (%s)",
            rule.rule_id, rule.standard.value,
        )

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a registered rule."""
        rule = self._rules.pop(rule_id, None)
        if rule is None:
            return False
        if rule.standard in self._rules_by_standard:
            try:
                self._rules_by_standard[rule.standard].remove(rule_id)
            except ValueError:
                pass
        return True

    def install_default_rules(self) -> None:
        """Install the built-in compliance rules for all standards."""
        self._install_hipaa_rules()
        self._install_pci_dss_rules()
        self._install_soc2_rules()
        self._install_gdpr_rules()
        self._install_sox_rules()
        self._install_iso27001_rules()
        self._install_nist_rules()
        logger.info(
            "ComplianceChecker: Installed %d default rules", len(self._rules)
        )

    # ── Compliance Checking ──────────────────────────────────

    def check(
        self,
        standard: ComplianceStandard,
        context: Dict[str, Any],
    ) -> ComplianceResult:
        """
        Check compliance against a specific standard.

        Args:
            standard: The compliance standard to check.
            context: Dictionary with data to validate.

        Returns:
            ComplianceResult with violations found.
        """
        start = time.monotonic()
        rule_ids = self._rules_by_standard.get(standard, [])
        violations: List[ComplianceViolation] = []
        warnings: List[str] = []

        if not rule_ids:
            warnings.append(f"No rules registered for standard '{standard.value}'")

        for rid in rule_ids:
            rule = self._rules.get(rid)
            if rule is None:
                continue
            violation = rule.check(context)
            if violation is not None:
                violations.append(violation)

        elapsed = (time.monotonic() - start) * 1000
        result = ComplianceResult(
            compliant=len(violations) == 0,
            standard=standard,
            violations=violations,
            warnings=warnings,
            duration_ms=elapsed,
        )

        self._audit_trail.append(result)
        logger.info(
            "ComplianceChecker: %s (standard=%s, violations=%d, %.1fms)",
            "PASS" if result.compliant else "FAIL",
            standard.value, len(violations), elapsed,
        )
        return result

    def check_all(
        self,
        context: Dict[str, Any],
        standards: Optional[List[ComplianceStandard]] = None,
    ) -> Dict[ComplianceStandard, ComplianceResult]:
        """
        Check compliance against multiple standards.

        Args:
            context: Dictionary with data to validate.
            standards: List of standards to check (None = all registered).

        Returns:
            Dict mapping each standard to its ComplianceResult.
        """
        if standards is None:
            standards = list(self._rules_by_standard.keys())

        results: Dict[ComplianceStandard, ComplianceResult] = {}
        for std in standards:
            results[std] = self.check(std, context)
        return results

    def check_pipeline(
        self,
        pipeline_context: Dict[str, Any],
        required_standards: Optional[List[ComplianceStandard]] = None,
    ) -> Dict[ComplianceStandard, ComplianceResult]:
        """
        Check pipeline-level compliance.

        Convenience method that extracts pipeline metadata and
        runs compliance checks.

        Args:
            pipeline_context: Pipeline context with keys like:
                data_sensitivity, encryption_enabled, audit_logging,
                access_controls, data_retention_days, etc.
            required_standards: Standards required for this pipeline.

        Returns:
            Dict mapping each standard to its ComplianceResult.
        """
        return self.check_all(pipeline_context, required_standards)

    # ── Built-in Rule Installers ─────────────────────────────

    def _install_hipaa_rules(self) -> None:
        """Install HIPAA compliance rules."""
        std = ComplianceStandard.HIPAA
        rules = [
            ComplianceRule(
                rule_id="hipaa.encryption_at_rest",
                standard=std,
                description="PHI must be encrypted at rest",
                severity=ComplianceSeverity.CRITICAL,
                check_fn=lambda ctx: ctx.get("encryption_at_rest", False),
                remediation="Enable encryption for all data stores containing PHI.",
            ),
            ComplianceRule(
                rule_id="hipaa.encryption_in_transit",
                standard=std,
                description="PHI must be encrypted in transit",
                severity=ComplianceSeverity.CRITICAL,
                check_fn=lambda ctx: ctx.get("encryption_in_transit", False),
                remediation="Enable TLS for all data transmission channels.",
            ),
            ComplianceRule(
                rule_id="hipaa.access_controls",
                standard=std,
                description="Access controls must be implemented for PHI",
                severity=ComplianceSeverity.HIGH,
                check_fn=lambda ctx: ctx.get("access_controls", False),
                remediation="Implement role-based access controls.",
            ),
            ComplianceRule(
                rule_id="hipaa.audit_logging",
                standard=std,
                description="Audit logging must be enabled for PHI access",
                severity=ComplianceSeverity.HIGH,
                check_fn=lambda ctx: ctx.get("audit_logging", False),
                remediation="Enable comprehensive audit logging.",
            ),
            ComplianceRule(
                rule_id="hipaa.minimum_necessary",
                standard=std,
                description="Only minimum necessary PHI should be accessed",
                severity=ComplianceSeverity.MEDIUM,
                check_fn=lambda ctx: ctx.get("minimum_necessary", True),
                remediation="Implement data minimization controls.",
            ),
        ]
        for rule in rules:
            self.add_rule(rule)

    def _install_pci_dss_rules(self) -> None:
        """Install PCI-DSS compliance rules."""
        std = ComplianceStandard.PCI_DSS
        rules = [
            ComplianceRule(
                rule_id="pci_dss.card_data_encryption",
                standard=std,
                description="Cardholder data must be encrypted",
                severity=ComplianceSeverity.CRITICAL,
                check_fn=lambda ctx: ctx.get("card_data_encrypted", False),
                remediation="Encrypt all cardholder data at rest and in transit.",
            ),
            ComplianceRule(
                rule_id="pci_dss.network_segmentation",
                standard=std,
                description="Cardholder data environment must be segmented",
                severity=ComplianceSeverity.HIGH,
                check_fn=lambda ctx: ctx.get("network_segmentation", False),
                remediation="Implement network segmentation for CDE.",
            ),
            ComplianceRule(
                rule_id="pci_dss.vulnerability_scanning",
                standard=std,
                description="Regular vulnerability scans must be performed",
                severity=ComplianceSeverity.HIGH,
                check_fn=lambda ctx: ctx.get("vulnerability_scanning", False),
                remediation="Schedule regular vulnerability scans.",
            ),
            ComplianceRule(
                rule_id="pci_dss.strong_authentication",
                standard=std,
                description="Strong authentication must be used for CDE access",
                severity=ComplianceSeverity.HIGH,
                check_fn=lambda ctx: ctx.get("strong_authentication", False),
                remediation="Implement MFA for all CDE access.",
            ),
        ]
        for rule in rules:
            self.add_rule(rule)

    def _install_soc2_rules(self) -> None:
        """Install SOC 2 compliance rules."""
        std = ComplianceStandard.SOC2
        rules = [
            ComplianceRule(
                rule_id="soc2.logical_access",
                standard=std,
                description="Logical access controls must be in place",
                severity=ComplianceSeverity.HIGH,
                check_fn=lambda ctx: ctx.get("logical_access_controls", False),
                remediation="Implement logical access controls.",
            ),
            ComplianceRule(
                rule_id="soc2.change_management",
                standard=std,
                description="Change management procedures must be followed",
                severity=ComplianceSeverity.MEDIUM,
                check_fn=lambda ctx: ctx.get("change_management", True),
                remediation="Implement formal change management procedures.",
            ),
            ComplianceRule(
                rule_id="soc2.incident_response",
                standard=std,
                description="Incident response plan must be in place",
                severity=ComplianceSeverity.HIGH,
                check_fn=lambda ctx: ctx.get("incident_response_plan", False),
                remediation="Develop and test an incident response plan.",
            ),
        ]
        for rule in rules:
            self.add_rule(rule)

    def _install_gdpr_rules(self) -> None:
        """Install GDPR compliance rules."""
        std = ComplianceStandard.GDPR
        rules = [
            ComplianceRule(
                rule_id="gdpr.consent_management",
                standard=std,
                description="Consent must be obtained for personal data processing",
                severity=ComplianceSeverity.HIGH,
                check_fn=lambda ctx: ctx.get("consent_management", False),
                remediation="Implement consent management system.",
            ),
            ComplianceRule(
                rule_id="gdpr.right_to_erasure",
                standard=std,
                description="Right to erasure must be supported",
                severity=ComplianceSeverity.HIGH,
                check_fn=lambda ctx: ctx.get("right_to_erasure", False),
                remediation="Implement data deletion capabilities.",
            ),
            ComplianceRule(
                rule_id="gdpr.data_minimization",
                standard=std,
                description="Only necessary personal data should be collected",
                severity=ComplianceSeverity.MEDIUM,
                check_fn=lambda ctx: ctx.get("data_minimization", True),
                remediation="Implement data minimization practices.",
            ),
            ComplianceRule(
                rule_id="gdpr.breach_notification",
                standard=std,
                description="Data breach notification procedures must be in place",
                severity=ComplianceSeverity.CRITICAL,
                check_fn=lambda ctx: ctx.get("breach_notification", False),
                remediation="Implement 72-hour breach notification procedures.",
            ),
        ]
        for rule in rules:
            self.add_rule(rule)

    def _install_sox_rules(self) -> None:
        """Install SOX compliance rules."""
        std = ComplianceStandard.SOX
        rules = [
            ComplianceRule(
                rule_id="sox.internal_controls",
                standard=std,
                description="Internal controls over financial reporting must exist",
                severity=ComplianceSeverity.HIGH,
                check_fn=lambda ctx: ctx.get("internal_controls", False),
                remediation="Implement internal controls for financial reporting.",
            ),
            ComplianceRule(
                rule_id="sox.segregation_of_duties",
                standard=std,
                description="Segregation of duties must be enforced",
                severity=ComplianceSeverity.HIGH,
                check_fn=lambda ctx: ctx.get("segregation_of_duties", False),
                remediation="Implement role-based segregation of duties.",
            ),
            ComplianceRule(
                rule_id="sox.audit_trail",
                standard=std,
                description="Complete audit trail for financial data must exist",
                severity=ComplianceSeverity.CRITICAL,
                check_fn=lambda ctx: ctx.get("financial_audit_trail", False),
                remediation="Implement tamper-proof audit trail for financial data.",
            ),
        ]
        for rule in rules:
            self.add_rule(rule)

    def _install_iso27001_rules(self) -> None:
        """Install ISO 27001 compliance rules."""
        std = ComplianceStandard.ISO_27001
        rules = [
            ComplianceRule(
                rule_id="iso27001.risk_assessment",
                standard=std,
                description="Information security risk assessment must be performed",
                severity=ComplianceSeverity.HIGH,
                check_fn=lambda ctx: ctx.get("risk_assessment", False),
                remediation="Conduct regular information security risk assessments.",
            ),
            ComplianceRule(
                rule_id="iso27001.security_policy",
                standard=std,
                description="Information security policy must be defined",
                severity=ComplianceSeverity.MEDIUM,
                check_fn=lambda ctx: ctx.get("security_policy", False),
                remediation="Define and maintain information security policy.",
            ),
        ]
        for rule in rules:
            self.add_rule(rule)

    def _install_nist_rules(self) -> None:
        """Install NIST compliance rules."""
        std = ComplianceStandard.NIST
        rules = [
            ComplianceRule(
                rule_id="nist.identify",
                standard=std,
                description="Asset management and risk assessment must be in place",
                severity=ComplianceSeverity.HIGH,
                check_fn=lambda ctx: ctx.get("asset_management", False),
                remediation="Implement asset management and risk identification.",
            ),
            ComplianceRule(
                rule_id="nist.protect",
                standard=std,
                description="Access controls and data security must be implemented",
                severity=ComplianceSeverity.HIGH,
                check_fn=lambda ctx: ctx.get("access_controls", False),
                remediation="Implement access controls and data protection.",
            ),
            ComplianceRule(
                rule_id="nist.detect",
                standard=std,
                description="Security event detection must be in place",
                severity=ComplianceSeverity.MEDIUM,
                check_fn=lambda ctx: ctx.get("anomaly_detection", False),
                remediation="Implement security monitoring and anomaly detection.",
            ),
            ComplianceRule(
                rule_id="nist.respond",
                standard=std,
                description="Incident response procedures must be defined",
                severity=ComplianceSeverity.HIGH,
                check_fn=lambda ctx: ctx.get("incident_response", False),
                remediation="Define and test incident response procedures.",
            ),
            ComplianceRule(
                rule_id="nist.recover",
                standard=std,
                description="Recovery planning must be in place",
                severity=ComplianceSeverity.MEDIUM,
                check_fn=lambda ctx: ctx.get("recovery_planning", False),
                remediation="Implement recovery planning and procedures.",
            ),
        ]
        for rule in rules:
            self.add_rule(rule)

    # ── Accessors ────────────────────────────────────────────

    @property
    def registered_standards(self) -> Set[ComplianceStandard]:
        """Set of standards with registered rules."""
        return set(self._rules_by_standard.keys())

    @property
    def rule_count(self) -> int:
        """Total number of registered rules."""
        return len(self._rules)

    @property
    def audit_trail(self) -> List[ComplianceResult]:
        """Compliance check audit trail."""
        return list(self._audit_trail)

    @property
    def stats(self) -> Dict[str, Any]:
        """Runtime statistics."""
        std_counts = {
            std.value: len(rules)
            for std, rules in self._rules_by_standard.items()
        }
        return {
            "total_rules": len(self._rules),
            "standards": std_counts,
            "audit_trail_length": len(self._audit_trail),
        }

    def clear(self) -> None:
        """Clear all rules and audit trail."""
        self._rules.clear()
        self._rules_by_standard.clear()
        self._audit_trail.clear()

    def __repr__(self) -> str:
        return (
            f"ComplianceChecker(rules={self.rule_count}, "
            f"standards={len(self._rules_by_standard)})"
        )
