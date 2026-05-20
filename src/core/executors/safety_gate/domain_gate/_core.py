"""
DomainSafetyGate — Core class and global instance.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ._helpers import (
    ComplianceResult,
    DomainSafetyCheckResult,
    _COMPILED_DOMAIN_RULES,
    _COMPLIANCE_CHECKERS,
    _PYTHON_DOMAIN_RULES,
    _escalate_verdict,
    _sensitivity_escalate,
)

logger = logging.getLogger(__name__)


class DomainSafetyGate:
    """
    Extended safety gate with domain-specific rules and compliance validation.

    Adds 35 niche-specific safety rules (5 per NicheCategory) and
    compliance validation engines on top of the base SafetyGate.

    INVARIANT: If the base gate returns DENY, the domain gate
    CANNOT override it. Domain rules can only ESCALATE verdicts.
    """

    # Compliance standards per niche category
    CATEGORY_COMPLIANCE: Dict[str, List[str]] = {
        "ai_data": ["gdpr", "iso_27001", "soc2"],
        "fintech": ["pci_dss", "aml_kyc", "sox", "gdpr"],
        "healthtech": ["hipaa", "gdpr", "soc2"],
        "greentech": ["iso_27001", "gdpr"],
        "edtech": ["coppa", "gdpr", "soc2"],
        "proptech": ["gdpr", "sox", "iso_27001"],
        "legaltech": ["sox", "soc2", "gdpr", "iso_27001"],
    }

    def __init__(self) -> None:
        self._native = None
        self._base_gate = None

    def _get_native(self):
        """Lazy-load the _zenic_native Rust extension."""
        if self._native is None:
            try:
                import _zenic_native as _native_mod  # type: ignore[import-not-found]
                self._native = _native_mod
            except ImportError:
                self._native = None
        return self._native

    def _get_base_gate(self):
        """Lazy-load the base SafetyGate."""
        if self._base_gate is None:
            from .._gate import get_default_safety_gate
            self._base_gate = get_default_safety_gate()
        return self._base_gate

    def check(
        self,
        action_type: str,
        config: Dict[str, Any],
        niche_category: str,
        data_sensitivity: str = "low",
    ) -> DomainSafetyCheckResult:
        """
        Run the full 4-layer extended safety validation.

        Tries Rust backend first, falls back to Python implementation.

        Parameters
        ----------
        action_type : str
            The type of action being performed.
        config : dict
            Configuration dict with action-specific parameters.
        niche_category : str
            NicheCategory string (e.g., "fintech", "healthtech").
        data_sensitivity : str
            DataSensitivity level ("low", "medium", "high", "critical").

        Returns
        -------
        DomainSafetyCheckResult
            Extended safety check result with domain and compliance info.
        """
        native = self._get_native()

        if native is not None:
            try:
                return self._rust_check(
                    native, action_type, config, niche_category, data_sensitivity
                )
            except Exception as e:
                logger.warning(f"Rust safety_validate_extended failed: {e}, using Python fallback")

        return self._python_check(
            action_type, config, niche_category, data_sensitivity
        )

    def _rust_check(
        self,
        native: Any,
        action_type: str,
        config: Dict[str, Any],
        niche_category: str,
        data_sensitivity: str,
    ) -> DomainSafetyCheckResult:
        """Use the Rust-compiled extended safety gate."""
        result = native.safety_validate_extended(
            action_type, config, niche_category, data_sensitivity
        )

        compliance_results = []
        for cr in result.compliance_results:
            compliance_results.append(ComplianceResult(
                standard=cr.standard,
                compliant=cr.compliant,
                violations=cr.violations,
                recommendations=cr.recommendations,
                risk_level=cr.risk_level,
            ))

        return DomainSafetyCheckResult(
            base_verdict=result.base_verdict,
            domain_verdict=result.domain_verdict,
            final_verdict=result.final_verdict,
            niche_category=result.niche_category,
            data_sensitivity=result.data_sensitivity,
            domain_rules_matched=result.domain_rules_matched,
            compliance_results=compliance_results,
            escalation_applied=result.escalation_applied,
            reason=result.reason,
            can_proceed=result.can_proceed,
        )

    def _python_check(
        self,
        action_type: str,
        config: Dict[str, Any],
        niche_category: str,
        data_sensitivity: str,
    ) -> DomainSafetyCheckResult:
        """Pure Python fallback — mirrors the Rust 4-layer pipeline exactly."""
        # ── Layer 1: Base SafetyGate ────────────────────────────
        base_gate = self._get_base_gate()
        base_result = base_gate.check(action_type, config)
        base_verdict_str = base_result.verdict.value

        # INVARIANT: Base DENY cannot be overridden
        if base_verdict_str == "DENY":
            return DomainSafetyCheckResult(
                base_verdict=base_verdict_str,
                domain_verdict=base_verdict_str,
                final_verdict=base_verdict_str,
                niche_category=niche_category,
                data_sensitivity=data_sensitivity,
                domain_rules_matched=[],
                compliance_results=[],
                escalation_applied=False,
                reason="Base gate DENY — cannot override",
                can_proceed=False,
            )

        current_verdict = base_verdict_str
        reason = base_result.reason

        # ── Layer 2: Domain-specific rules ──────────────────────
        searchable = self._to_searchable(action_type, config)
        domain_rules_matched: List[str] = []
        domain_verdict = current_verdict

        for rule in _COMPILED_DOMAIN_RULES:
            if rule["category"] != niche_category:
                continue
            if rule["compiled"].search(searchable):
                domain_verdict = _escalate_verdict(domain_verdict, rule["verdict"])
                domain_rules_matched.append(rule["name"])
                reason = rule["message"]

        current_verdict = domain_verdict

        # ── Layer 3: Compliance validation ──────────────────────
        config_str = searchable.lower()
        standards = self.CATEGORY_COMPLIANCE.get(niche_category, [])
        compliance_results: List[ComplianceResult] = []

        for std in standards:
            checker = _COMPLIANCE_CHECKERS.get(std)
            if checker is not None:
                try:
                    cr = checker(config_str)
                    compliance_results.append(cr)
                except Exception:
                    # SECURITY: Fail closed — if checker fails, assume non-compliant
                    compliance_results.append(ComplianceResult(standard=std, compliant=False, risk_level="critical"))

        # Critical compliance violations → DENY
        for cr in compliance_results:
            if cr.risk_level == "critical" and not cr.compliant:
                current_verdict = "DENY"
                reason = f"Critical compliance violation ({cr.standard}): {cr.violations[0] if cr.violations else 'Unknown'}"
                break

        # ── Layer 4: Sensitivity escalation ─────────────────────
        final_verdict, escalation_applied = _sensitivity_escalate(current_verdict, data_sensitivity)

        if escalation_applied:
            reason = f"{reason} [sensitivity escalation: {current_verdict} → {final_verdict} due to {data_sensitivity} sensitivity]"

        can_proceed = final_verdict not in ("DENY", "RATE_LIMITED")

        return DomainSafetyCheckResult(
            base_verdict=base_verdict_str,
            domain_verdict=domain_verdict,
            final_verdict=final_verdict,
            niche_category=niche_category,
            data_sensitivity=data_sensitivity,
            domain_rules_matched=domain_rules_matched,
            compliance_results=compliance_results,
            escalation_applied=escalation_applied,
            reason=reason,
            can_proceed=can_proceed,
        )

    def _to_searchable(self, action_type: str, config: Dict[str, Any]) -> str:
        """Convert action_type + config to a searchable string."""
        parts = [action_type]
        for key, value in config.items():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, (list, tuple)):
                parts.extend(str(v) for v in value)
            else:
                parts.append(str(value))
        return " ".join(parts)

    def get_domain_rules(self, niche_category: str) -> List[Dict[str, Any]]:
        """Get all domain safety rules for a niche category."""
        native = self._get_native()
        if native is not None:
            try:
                rules = native.safety_get_domain_rules(niche_category)
                return [
                    {
                        "name": r.name,
                        "niche_category": r.niche_category,
                        "verdict": r.verdict,
                        "message": r.message,
                        "compliance_standards": r.compliance_standards,
                    }
                    for r in rules
                ]
            except Exception:
                pass
        # Python fallback
        return [
            {
                "name": r["name"],
                "niche_category": r["category"],
                "verdict": r["verdict"],
                "message": r["message"],
            }
            for r in _PYTHON_DOMAIN_RULES
            if r["category"] == niche_category
        ]

    def get_compliance_for_category(self, niche_category: str) -> List[str]:
        """Get compliance standards required for a niche category."""
        native = self._get_native()
        if native is not None:
            try:
                return native.safety_get_compliance_for_category(niche_category)
            except Exception:
                pass
        return self.CATEGORY_COMPLIANCE.get(niche_category, [])


# ── Global Instance ──────────────────────────────────────

_default_domain_gate: Optional[DomainSafetyGate] = None


def get_default_domain_safety_gate() -> DomainSafetyGate:
    """Get or create the global DomainSafetyGate instance."""
    global _default_domain_gate
    if _default_domain_gate is None:
        _default_domain_gate = DomainSafetyGate()
    return _default_domain_gate
