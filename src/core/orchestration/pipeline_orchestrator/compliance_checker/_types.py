"""
Compliance Checker — Data contracts: enums, violation, result, and rule types.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


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
                # SECURITY: Preserve the rule's original severity on error.
                # Downgrading to LOW would be a fail-open: a CRITICAL rule
                # whose check_fn raises would be silently treated as low-risk,
                # allowing non-compliant operations to proceed unchecked.
                severity=self.severity,
                description=f"Rule check error: {exc}",
                remediation="Fix the rule implementation or context data.",
            )
