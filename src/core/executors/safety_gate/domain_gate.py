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

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ._types import SafetyVerdict, ActionCategory

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  Compliance Result
# ──────────────────────────────────────────────────────────────

class ComplianceResult:
    """Result of a compliance check against a regulatory standard."""

    __slots__ = ("standard", "compliant", "violations", "recommendations", "risk_level")

    def __init__(
        self,
        standard: str = "",
        compliant: bool = True,
        violations: Optional[List[str]] = None,
        recommendations: Optional[List[str]] = None,
        risk_level: str = "low",
    ) -> None:
        self.standard = standard
        self.compliant = compliant
        self.violations = violations or []
        self.recommendations = recommendations or []
        self.risk_level = risk_level

    def __repr__(self) -> str:
        return (
            f"ComplianceResult(standard={self.standard!r}, "
            f"compliant={self.compliant}, violations={len(self.violations)})"
        )


# ──────────────────────────────────────────────────────────────
#  Domain Safety Check Result
# ──────────────────────────────────────────────────────────────

class DomainSafetyCheckResult:
    """Result of the extended domain safety check."""

    __slots__ = (
        "base_verdict",
        "domain_verdict",
        "final_verdict",
        "niche_category",
        "data_sensitivity",
        "domain_rules_matched",
        "compliance_results",
        "escalation_applied",
        "reason",
        "can_proceed",
    )

    def __init__(
        self,
        base_verdict: str = "ALLOW",
        domain_verdict: str = "ALLOW",
        final_verdict: str = "ALLOW",
        niche_category: str = "",
        data_sensitivity: str = "low",
        domain_rules_matched: Optional[List[str]] = None,
        compliance_results: Optional[List[ComplianceResult]] = None,
        escalation_applied: bool = False,
        reason: str = "",
        can_proceed: bool = True,
    ) -> None:
        self.base_verdict = base_verdict
        self.domain_verdict = domain_verdict
        self.final_verdict = final_verdict
        self.niche_category = niche_category
        self.data_sensitivity = data_sensitivity
        self.domain_rules_matched = domain_rules_matched or []
        self.compliance_results = compliance_results or []
        self.escalation_applied = escalation_applied
        self.reason = reason
        self.can_proceed = can_proceed

    def __repr__(self) -> str:
        return (
            f"DomainSafetyCheckResult(final={self.final_verdict}, "
            f"category={self.niche_category!r}, "
            f"escalation={self.escalation_applied}, "
            f"can_proceed={self.can_proceed})"
        )


# ──────────────────────────────────────────────────────────────
#  Python Fallback: Domain Rules (35 rules)
# ──────────────────────────────────────────────────────────────

_PYTHON_DOMAIN_RULES: List[Dict[str, Any]] = [
    # ── AI & Data Analytics (5) ──────────────────────────────
    {"name": "ai_data_model_retrain", "category": "ai_data", "pattern": r"(?:retrain|re-train|model_update|model_refresh)", "verdict": "APPROVE", "message": "ML model retraining requires approval"},
    {"name": "ai_data_bulk_export", "category": "ai_data", "pattern": r"(?:bulk_export|mass_export|download_all|export_dataset)", "verdict": "CONFIRM", "message": "Bulk data export requires confirmation"},
    {"name": "ai_data_pii_access", "category": "ai_data", "pattern": r"(?:pii|personal_data|sensitive_data|personally_identifiable)", "verdict": "APPROVE", "message": "PII data access requires approval"},
    {"name": "ai_data_pipeline_config", "category": "ai_data", "pattern": r"(?:pipeline_config|etl_change|data_flow_modify)", "verdict": "CONFIRM", "message": "Pipeline configuration change requires confirmation"},
    {"name": "ai_data_prediction_override", "category": "ai_data", "pattern": r"(?:prediction_override|manual_override|force_prediction|override_ai)", "verdict": "CONFIRM", "message": "Manual AI prediction override requires confirmation"},
    # ── FinTech (5) ──────────────────────────────────────────
    {"name": "fintech_unauthorized_transfer", "category": "fintech", "pattern": r"(?:transfer|send_money|wire|remittance).*(?:unauthorized|unverified|without_approval)", "verdict": "DENY", "message": "Unauthorized financial transfer — DENIED per AML/KYC"},
    {"name": "fintech_large_transaction", "category": "fintech", "pattern": r"(?:large_transaction|big_transfer|high_value).*(?:amount|value|sum)", "verdict": "APPROVE", "message": "Large transaction requires dual approval"},
    {"name": "fintech_rate_change", "category": "fintech", "pattern": r"(?:interest_rate|fee_change|rate_modify|apr_change|commission_update)", "verdict": "APPROVE", "message": "Rate modification requires approval"},
    {"name": "fintech_account_closure", "category": "fintech", "pattern": r"(?:account_close|close_account|terminate_account|account_closure)", "verdict": "CONFIRM", "message": "Account closure requires confirmation"},
    {"name": "fintech_compliance_bypass", "category": "fintech", "pattern": r"(?:bypass_compliance|skip_kyc|override_aml|ignore_check)", "verdict": "DENY", "message": "Compliance bypass attempt — ABSOLUTELY DENIED"},
    # ── HealthTech (5) ───────────────────────────────────────
    {"name": "healthtech_phi_access", "category": "healthtech", "pattern": r"(?:phi|health_record|medical_record|patient_data|clinical_data)", "verdict": "APPROVE", "message": "PHI access requires approval — HIPAA compliance"},
    {"name": "healthtech_prescription_mod", "category": "healthtech", "pattern": r"(?:prescription|medication).*(?:modify|change|update|alter)", "verdict": "DENY", "message": "Unauthorized prescription modification — DENIED"},
    {"name": "healthtech_diagnosis_override", "category": "healthtech", "pattern": r"(?:diagnosis_override|override_diagnosis|clinical_override|force_diagnosis)", "verdict": "APPROVE", "message": "Diagnosis override requires medical professional approval"},
    {"name": "healthtech_patient_export", "category": "healthtech", "pattern": r"(?:patient_export|export_patient|download_records|medical_data_export)", "verdict": "CONFIRM", "message": "Patient data export requires confirmation"},
    {"name": "healthtech_device_config", "category": "healthtech", "pattern": r"(?:device_config|wearable_config|monitor_setup|device_calibration)", "verdict": "CONFIRM", "message": "Medical device configuration change requires confirmation"},
    # ── GreenTech (5) ────────────────────────────────────────
    {"name": "greentech_carbon_adjust", "category": "greentech", "pattern": r"(?:carbon_credit|credit_adjust|offset_modify|emission_offset)", "verdict": "APPROVE", "message": "Carbon credit adjustment requires approval"},
    {"name": "greentech_grid_reconfig", "category": "greentech", "pattern": r"(?:grid_reconfig|smart_grid_change|load_balance_modify|grid_topology)", "verdict": "CONFIRM", "message": "Grid reconfiguration requires confirmation"},
    {"name": "greentech_sensor_override", "category": "greentech", "pattern": r"(?:sensor_override|override_sensor|bypass_monitor|ignore_reading)", "verdict": "CONFIRM", "message": "Sensor override requires confirmation"},
    {"name": "greentech_waste_reclassify", "category": "greentech", "pattern": r"(?:waste_reclassify|reclassify_waste|waste_category_change|hazardous_reclass)", "verdict": "APPROVE", "message": "Waste reclassification requires approval"},
    {"name": "greentech_fleet_decommission", "category": "greentech", "pattern": r"(?:fleet_decommission|decommission_ev|retire_vehicle|fleet_remove)", "verdict": "CONFIRM", "message": "Fleet decommission requires confirmation"},
    # ── EdTech (5) ───────────────────────────────────────────
    {"name": "edtech_minor_data", "category": "edtech", "pattern": r"(?:minor_data|student_data|child_data|underage|under_18)", "verdict": "APPROVE", "message": "Minor data access requires approval — COPPA compliance"},
    {"name": "edtech_grade_modify", "category": "edtech", "pattern": r"(?:grade_modify|change_grade|assessment_override|score_change)", "verdict": "DENY", "message": "Unauthorized grade modification — DENIED"},
    {"name": "edtech_content_filter", "category": "edtech", "pattern": r"(?:filter_bypass|bypass_filter|content_unblock|unblock_site)", "verdict": "DENY", "message": "Content filter bypass — DENIED"},
    {"name": "edtech_bulk_export", "category": "edtech", "pattern": r"(?:bulk_student_export|export_roster|download_grades|class_export)", "verdict": "CONFIRM", "message": "Bulk student data export requires confirmation"},
    {"name": "edtech_curriculum_change", "category": "edtech", "pattern": r"(?:curriculum_change|course_modify|syllabus_update|learning_path_change)", "verdict": "CONFIRM", "message": "Curriculum change requires confirmation"},
    # ── PropTech (5) ─────────────────────────────────────────
    {"name": "proptech_transaction", "category": "proptech", "pattern": r"(?:property_transaction|real_estate_deal|buy_property|sell_property)", "verdict": "APPROVE", "message": "Property transaction requires approval"},
    {"name": "proptech_lease_terminate", "category": "proptech", "pattern": r"(?:lease_terminate|terminate_lease|cancel_lease|early_termination)", "verdict": "CONFIRM", "message": "Lease termination requires confirmation"},
    {"name": "proptech_valuation_change", "category": "proptech", "pattern": r"(?:valuation_change|appraisal_modify|value_adjust|price_revalue)", "verdict": "APPROVE", "message": "Valuation change requires approval"},
    {"name": "proptech_tenant_data", "category": "proptech", "pattern": r"(?:tenant_data|tenant_info|renter_data|occupant_info)", "verdict": "CONFIRM", "message": "Tenant data access requires confirmation"},
    {"name": "proptech_access_control", "category": "proptech", "pattern": r"(?:access_control|door_config|security_system|building_access)", "verdict": "CONFIRM", "message": "Access control modification requires confirmation"},
    # ── LegalTech (5) ────────────────────────────────────────
    {"name": "legaltech_contract_exec", "category": "legaltech", "pattern": r"(?:contract_execute|execute_contract|sign_contract|contract_sign)", "verdict": "APPROVE", "message": "Contract execution requires approval"},
    {"name": "legaltech_document_delete", "category": "legaltech", "pattern": r"(?:document_delete|delete_legal|destroy_record|purge_document)", "verdict": "DENY", "message": "Legal document deletion — DENIED"},
    {"name": "legaltech_privilege", "category": "legaltech", "pattern": r"(?:privilege|attorney_client|legal_privilege|work_product)", "verdict": "APPROVE", "message": "Privileged data access requires approval"},
    {"name": "legaltech_compliance_config", "category": "legaltech", "pattern": r"(?:compliance_config|monitor_change|alert_threshold|compliance_rule_modify)", "verdict": "CONFIRM", "message": "Compliance config change requires confirmation"},
    {"name": "legaltech_ip_transfer", "category": "legaltech", "pattern": r"(?:ip_transfer|patent_transfer|trademark_assign|copyright_transfer)", "verdict": "APPROVE", "message": "IP transfer requires approval"},
]

# Pre-compile regex patterns
_COMPILED_DOMAIN_RULES: List[Dict[str, Any]] = []
for _rule in _PYTHON_DOMAIN_RULES:
    _compiled = _rule.copy()
    _compiled["compiled"] = re.compile(_rule["pattern"], re.IGNORECASE)
    _COMPILED_DOMAIN_RULES.append(_compiled)


# ──────────────────────────────────────────────────────────────
#  Python Fallback: Compliance Checks
# ──────────────────────────────────────────────────────────────

def _check_compliance_hipaa(config_str: str) -> ComplianceResult:
    """Check HIPAA compliance (deterministic)."""
    violations = []
    recommendations = []
    risk_level = "low"

    if "phi" in config_str or "health_record" in config_str or "patient_data" in config_str:
        if "encryption" not in config_str and "encrypted" not in config_str:
            violations.append("PHI access without encryption — HIPAA Security Rule violation")
            recommendations.append("Enable encryption for all PHI data access")
            risk_level = "critical"
        if "audit" not in config_str and "logged" not in config_str:
            violations.append("PHI access without audit trail — HIPAA Audit Control requirement")
            recommendations.append("Enable audit logging for all PHI access events")
            if risk_level != "critical":
                risk_level = "high"

    if violations:
        return ComplianceResult("hipaa", False, violations, recommendations, risk_level)
    return ComplianceResult("hipaa", True, risk_level="low")


def _check_compliance_pci_dss(config_str: str) -> ComplianceResult:
    """Check PCI-DSS compliance (deterministic)."""
    violations = []
    recommendations = []
    risk_level = "low"

    if "card" in config_str or "credit" in config_str or "pan" in config_str:
        if "tokeniz" not in config_str and "token" not in config_str:
            violations.append("Card data processing without tokenization — PCI-DSS Requirement 3")
            recommendations.append("Use tokenization for all card data storage and processing")
            risk_level = "critical"

    if violations:
        return ComplianceResult("pci_dss", False, violations, recommendations, risk_level)
    return ComplianceResult("pci_dss", True, risk_level="low")


def _check_compliance_gdpr(config_str: str) -> ComplianceResult:
    """Check GDPR compliance (deterministic)."""
    violations = []
    recommendations = []
    risk_level = "low"

    if "personal_data" in config_str or "pii" in config_str or "user_data" in config_str:
        if "consent" not in config_str and "legal_basis" not in config_str and "legitimate_interest" not in config_str:
            violations.append("Personal data processing without documented legal basis — GDPR Article 6")
            recommendations.append("Document legal basis for data processing")
            risk_level = "high"

    if violations:
        return ComplianceResult("gdpr", False, violations, recommendations, risk_level)
    return ComplianceResult("gdpr", True, risk_level="low")


def _check_compliance_sox(config_str: str) -> ComplianceResult:
    """Check SOX compliance (deterministic)."""
    violations = []
    recommendations = []
    risk_level = "low"

    if "financial_report" in config_str or "accounting" in config_str or "ledger" in config_str:
        if "dual_control" not in config_str and "segregation" not in config_str and "approval" not in config_str:
            violations.append("Financial data modification without dual control — SOX Section 404")
            recommendations.append("Implement dual control for financial modifications")
            risk_level = "critical"

    if violations:
        return ComplianceResult("sox", False, violations, recommendations, risk_level)
    return ComplianceResult("sox", True, risk_level="low")


def _check_compliance_aml_kyc(config_str: str) -> ComplianceResult:
    """Check AML/KYC compliance (deterministic)."""
    violations = []
    recommendations = []
    risk_level = "low"

    if "transfer" in config_str or "transaction" in config_str or "payment" in config_str:
        if "kyc_verified" not in config_str and "kyc_check" not in config_str and "identity_verified" not in config_str:
            violations.append("Financial transaction without KYC verification — AML compliance risk")
            recommendations.append("Verify customer identity before processing transactions")
            risk_level = "critical"

    if violations:
        return ComplianceResult("aml_kyc", False, violations, recommendations, risk_level)
    return ComplianceResult("aml_kyc", True, risk_level="low")


def _check_compliance_coppa(config_str: str) -> ComplianceResult:
    """Check COPPA compliance (deterministic)."""
    violations = []
    recommendations = []
    risk_level = "low"

    if "minor" in config_str or "child" in config_str or "under_13" in config_str or "student" in config_str:
        if "parental_consent" not in config_str and "guardian_approval" not in config_str:
            violations.append("Children's data collection without parental consent — COPPA Section 3")
            recommendations.append("Obtain verifiable parental consent before collecting children's data")
            risk_level = "critical"

    if violations:
        return ComplianceResult("coppa", False, violations, recommendations, risk_level)
    return ComplianceResult("coppa", True, risk_level="low")


def _check_compliance_iso_27001(config_str: str) -> ComplianceResult:
    """Check ISO 27001 compliance (deterministic)."""
    violations = []
    recommendations = []
    risk_level = "low"

    if "config_change" in config_str or "system_modify" in config_str or "infrastructure_change" in config_str:
        if "change_management" not in config_str and "change_request" not in config_str and "approval" not in config_str:
            violations.append("System change without change management — ISO 27001 Annex A.12")
            recommendations.append("Route system changes through formal change management process")
            risk_level = "high"

    if violations:
        return ComplianceResult("iso_27001", False, violations, recommendations, risk_level)
    return ComplianceResult("iso_27001", True, risk_level="low")


def _check_compliance_soc2(config_str: str) -> ComplianceResult:
    """Check SOC 2 compliance (deterministic)."""
    violations = []
    recommendations = []
    risk_level = "low"

    if "data_access" in config_str or "sensitive_data" in config_str or "api_key" in config_str:
        if "monitored" not in config_str and "audit" not in config_str and "logging" not in config_str:
            violations.append("Sensitive data access without monitoring — SOC 2 CC6.1")
            recommendations.append("Enable monitoring and audit logging for sensitive data access")
            risk_level = "high"

    if violations:
        return ComplianceResult("soc2", False, violations, recommendations, risk_level)
    return ComplianceResult("soc2", True, risk_level="low")


_COMPLIANCE_CHECKERS = {
    "hipaa": _check_compliance_hipaa,
    "pci_dss": _check_compliance_pci_dss,
    "gdpr": _check_compliance_gdpr,
    "sox": _check_compliance_sox,
    "aml_kyc": _check_compliance_aml_kyc,
    "coppa": _check_compliance_coppa,
    "iso_27001": _check_compliance_iso_27001,
    "soc2": _check_compliance_soc2,
}


# ──────────────────────────────────────────────────────────────
#  Verdict Escalation Helper
# ──────────────────────────────────────────────────────────────

_VERDICT_SEVERITY = {"ALLOW": 0, "CONFIRM": 1, "APPROVE": 2, "DENY": 3, "RATE_LIMITED": 3}


def _escalate_verdict(current: str, new: str) -> str:
    """Escalate verdict — only escalate, never downgrade."""
    if _VERDICT_SEVERITY.get(new, 0) > _VERDICT_SEVERITY.get(current, 0):
        return new
    return current


def _sensitivity_escalate(verdict: str, sensitivity: str) -> Tuple[str, bool]:
    """Apply sensitivity escalation. Returns (escalated_verdict, was_escalated)."""
    if sensitivity == "critical":
        if verdict == "ALLOW":
            return "CONFIRM", True
        if verdict == "CONFIRM":
            return "APPROVE", True
        if verdict == "APPROVE":
            return "DENY", True
    elif sensitivity == "high":
        if verdict == "ALLOW":
            return "CONFIRM", True
        if verdict == "CONFIRM":
            return "APPROVE", True
    return verdict, False


# ──────────────────────────────────────────────────────────────
#  DomainSafetyGate
# ──────────────────────────────────────────────────────────────

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
                from src.core.native import _zenic_native
                self._native = _zenic_native
            except ImportError:
                self._native = None
        return self._native

    def _get_base_gate(self):
        """Lazy-load the base SafetyGate."""
        if self._base_gate is None:
            from ._gate import get_default_safety_gate
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
                    compliance_results.append(ComplianceResult(standard=std, compliant=True, risk_level="low"))

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
