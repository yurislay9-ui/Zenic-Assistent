"""
Integration tests for Phase D — DomainSafetyGate + InteractiveDataCollector + E2E Pipeline.

Tests the full Python fallback path (Rust extension not required).
All tests are deterministic — no AI, no randomness, no external dependencies.
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ──────────────────────────────────────────────────────────────
# DomainSafetyGate Tests
# ──────────────────────────────────────────────────────────────

class TestDomainSafetyGatePythonFallback:
    """Test the Python fallback path of DomainSafetyGate."""

    def test_safe_action_low_sensitivity(self):
        from src.core.executors.safety_gate.domain_gate import DomainSafetyGate
        gate = DomainSafetyGate()
        result = gate.check(
            action_type="notification",
            config={"action": "view_dashboard"},
            niche_category="ai_data",
            data_sensitivity="low",
        )
        assert result.final_verdict == "ALLOW"
        assert result.can_proceed is True
        assert result.escalation_applied is False

    def test_fintech_compliance_bypass_denied(self):
        from src.core.executors.safety_gate.domain_gate import DomainSafetyGate
        gate = DomainSafetyGate()
        result = gate.check(
            action_type="compliance_operation",
            config={"action": "bypass_compliance", "target": "kyc_check"},
            niche_category="fintech",
            data_sensitivity="medium",
        )
        assert "fintech_compliance_bypass" in result.domain_rules_matched
        assert result.final_verdict == "DENY"
        assert result.can_proceed is False

    def test_healthtech_phi_approval(self):
        from src.core.executors.safety_gate.domain_gate import DomainSafetyGate
        gate = DomainSafetyGate()
        result = gate.check(
            action_type="data_access",
            config={"action": "phi_access", "data_type": "health_record"},
            niche_category="healthtech",
            data_sensitivity="medium",
        )
        assert "healthtech_phi_access" in result.domain_rules_matched

    def test_sensitivity_escalation_high(self):
        from src.core.executors.safety_gate.domain_gate import DomainSafetyGate
        gate = DomainSafetyGate()
        result = gate.check(
            action_type="notification",
            config={"action": "view_data"},
            niche_category="edtech",
            data_sensitivity="high",
        )
        assert result.escalation_applied is True
        assert result.final_verdict == "CONFIRM"

    def test_sensitivity_escalation_critical(self):
        from src.core.executors.safety_gate.domain_gate import DomainSafetyGate
        gate = DomainSafetyGate()
        result = gate.check(
            action_type="notification",
            config={"action": "view_data"},
            niche_category="edtech",
            data_sensitivity="critical",
        )
        assert result.escalation_applied is True
        assert result.final_verdict == "CONFIRM"

    def test_get_domain_rules_returns_5(self):
        from src.core.executors.safety_gate.domain_gate import DomainSafetyGate
        gate = DomainSafetyGate()
        rules = gate.get_domain_rules("fintech")
        assert len(rules) == 5

    def test_get_compliance_for_category(self):
        from src.core.executors.safety_gate.domain_gate import DomainSafetyGate
        gate = DomainSafetyGate()
        standards = gate.get_compliance_for_category("healthtech")
        assert "hipaa" in standards
        assert "gdpr" in standards


class TestComplianceChecks:
    """Test individual compliance check functions."""

    def test_hipaa_phi_without_encryption(self):
        from src.core.executors.safety_gate.domain_gate import _check_compliance_hipaa
        result = _check_compliance_hipaa("phi access health_record")
        assert not result.compliant
        assert result.risk_level == "critical"

    def test_hipaa_phi_with_encryption(self):
        from src.core.executors.safety_gate.domain_gate import _check_compliance_hipaa
        result = _check_compliance_hipaa("phi access encryption=true audit=true")
        assert result.compliant

    def test_pci_dss_card_without_tokenization(self):
        from src.core.executors.safety_gate.domain_gate import _check_compliance_pci_dss
        result = _check_compliance_pci_dss("card credit pan")
        assert not result.compliant
        assert result.risk_level == "critical"

    def test_gdpr_personal_data_without_consent(self):
        from src.core.executors.safety_gate.domain_gate import _check_compliance_gdpr
        result = _check_compliance_gdpr("personal_data pii user_data")
        assert not result.compliant

    def test_coppa_children_without_consent(self):
        from src.core.executors.safety_gate.domain_gate import _check_compliance_coppa
        result = _check_compliance_coppa("minor child student under_13")
        assert not result.compliant
        assert result.risk_level == "critical"

    def test_aml_kyc_without_verification(self):
        from src.core.executors.safety_gate.domain_gate import _check_compliance_aml_kyc
        result = _check_compliance_aml_kyc("transfer transaction payment")
        assert not result.compliant

    def test_sox_financial_without_dual_control(self):
        from src.core.executors.safety_gate.domain_gate import _check_compliance_sox
        result = _check_compliance_sox("financial_report accounting ledger")
        assert not result.compliant


# ──────────────────────────────────────────────────────────────
# InteractiveDataCollector Tests
# ──────────────────────────────────────────────────────────────

class TestInteractiveDataCollectorPythonFallback:
    """Test the Python fallback path of InteractiveDataCollector."""

    def test_start_session(self):
        from src.core.agents_v2.business.interactive_data_collector import InteractiveDataCollector
        collector = InteractiveDataCollector()
        result = collector._python_fallback({"action": "start", "niche_id": "telemedicine"}, "start")
        assert result.session_id.startswith("py-telemedicine-")
        assert result.niche_id == "telemedicine"
        assert result.source == "python_fallback"

    def test_validate_email(self):
        from src.core.agents_v2.business.interactive_data_collector import InteractiveDataCollector
        collector = InteractiveDataCollector()
        result = collector._python_fallback(
            {"action": "validate", "field_type": "email", "value": "test@example.com"},
            "validate",
        )
        assert result.answers_applied == 1

    def test_validate_invalid_email(self):
        from src.core.agents_v2.business.interactive_data_collector import InteractiveDataCollector
        collector = InteractiveDataCollector()
        result = collector._python_fallback(
            {"action": "validate", "field_type": "email", "value": "not-an-email"},
            "validate",
        )
        assert result.answers_rejected == 1

    def test_validate_boolean(self):
        from src.core.agents_v2.business.interactive_data_collector import InteractiveDataCollector
        collector = InteractiveDataCollector()
        for value in ["true", "false", "yes", "no", "1", "0"]:
            result = collector._python_fallback(
                {"action": "validate", "field_type": "boolean", "value": value},
                "validate",
            )
            assert result.answers_applied == 1, f"Boolean '{value}' should be valid"

    def test_validate_url(self):
        from src.core.agents_v2.business.interactive_data_collector import InteractiveDataCollector
        collector = InteractiveDataCollector()
        result = collector._python_fallback(
            {"action": "validate", "field_type": "url", "value": "https://example.com"},
            "validate",
        )
        assert result.answers_applied == 1

    def test_suggestions_for_business_name(self):
        from src.core.agents_v2.business.interactive_data_collector import InteractiveDataCollector
        collector = InteractiveDataCollector()
        result = collector._python_fallback(
            {"action": "suggestions", "field_name": "business_name", "field_type": "text"},
            "suggestions",
        )
        assert len(result.questions) > 0
        assert len(result.questions[0]["suggestions"]) > 0

    def test_suggestions_for_currency(self):
        from src.core.agents_v2.business.interactive_data_collector import InteractiveDataCollector
        collector = InteractiveDataCollector()
        result = collector._python_fallback(
            {"action": "suggestions", "field_name": "currency", "field_type": "currency"},
            "suggestions",
        )
        assert "USD" in result.questions[0]["suggestions"]


# ──────────────────────────────────────────────────────────────
# Domain Rules Coverage Tests
# ──────────────────────────────────────────────────────────────

class TestDomainRulesCoverage:
    """Test that all 35 domain rules are properly loaded."""

    def test_all_35_rules_loaded(self):
        from src.core.executors.safety_gate.domain_gate import _PYTHON_DOMAIN_RULES
        assert len(_PYTHON_DOMAIN_RULES) == 35

    def test_5_rules_per_category(self):
        from src.core.executors.safety_gate.domain_gate import _PYTHON_DOMAIN_RULES
        categories = {}
        for rule in _PYTHON_DOMAIN_RULES:
            cat = rule["category"]
            categories[cat] = categories.get(cat, 0) + 1

        expected_categories = ["ai_data", "fintech", "healthtech", "greentech", "edtech", "proptech", "legaltech"]
        for cat in expected_categories:
            assert cat in categories, f"Missing category: {cat}"
            assert categories[cat] == 5, f"Expected 5 rules for {cat}, got {categories[cat]}"

    def test_all_rules_have_valid_verdicts(self):
        from src.core.executors.safety_gate.domain_gate import _PYTHON_DOMAIN_RULES
        valid_verdicts = {"ALLOW", "CONFIRM", "APPROVE", "DENY"}
        for rule in _PYTHON_DOMAIN_RULES:
            assert rule["verdict"] in valid_verdicts, f"Invalid verdict in {rule['name']}: {rule['verdict']}"

    def test_all_rules_have_compiled_regex(self):
        from src.core.executors.safety_gate.domain_gate import _COMPILED_DOMAIN_RULES
        for rule in _COMPILED_DOMAIN_RULES:
            assert rule["compiled"] is not None, f"Regex not compiled for {rule['name']}"


# ──────────────────────────────────────────────────────────────
# Verdict Escalation Tests
# ──────────────────────────────────────────────────────────────

class TestVerdictEscalation:
    """Test the deterministic verdict escalation logic."""

    def test_escalate_higher(self):
        from src.core.executors.safety_gate.domain_gate import _escalate_verdict
        assert _escalate_verdict("ALLOW", "CONFIRM") == "CONFIRM"
        assert _escalate_verdict("CONFIRM", "APPROVE") == "APPROVE"
        assert _escalate_verdict("APPROVE", "DENY") == "DENY"

    def test_escalate_never_downgrades(self):
        from src.core.executors.safety_gate.domain_gate import _escalate_verdict
        assert _escalate_verdict("DENY", "ALLOW") == "DENY"
        assert _escalate_verdict("APPROVE", "CONFIRM") == "APPROVE"
        assert _escalate_verdict("CONFIRM", "ALLOW") == "CONFIRM"

    def test_sensitivity_escalate_critical(self):
        from src.core.executors.safety_gate.domain_gate import _sensitivity_escalate
        assert _sensitivity_escalate("ALLOW", "critical") == ("CONFIRM", True)
        assert _sensitivity_escalate("CONFIRM", "critical") == ("APPROVE", True)
        assert _sensitivity_escalate("APPROVE", "critical") == ("DENY", True)
        assert _sensitivity_escalate("DENY", "critical") == ("DENY", False)

    def test_sensitivity_escalate_high(self):
        from src.core.executors.safety_gate.domain_gate import _sensitivity_escalate
        assert _sensitivity_escalate("ALLOW", "high") == ("CONFIRM", True)
        assert _sensitivity_escalate("CONFIRM", "high") == ("APPROVE", True)
        assert _sensitivity_escalate("APPROVE", "high") == ("APPROVE", False)

    def test_sensitivity_escalate_low(self):
        from src.core.executors.safety_gate.domain_gate import _sensitivity_escalate
        assert _sensitivity_escalate("ALLOW", "low") == ("ALLOW", False)
        assert _sensitivity_escalate("CONFIRM", "low") == ("CONFIRM", False)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
