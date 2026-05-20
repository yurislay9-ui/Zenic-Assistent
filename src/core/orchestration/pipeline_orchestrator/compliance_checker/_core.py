"""compliance_checker — Core implementation."""

from __future__ import annotations

from ._types import *  # noqa: F403
from ._helpers import _install_hipaa_rules, _install_pci_dss_rules, _install_soc2_rules, _install_gdpr_rules, _install_sox_rules, _install_iso27001_rules, _install_nist_rules

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
