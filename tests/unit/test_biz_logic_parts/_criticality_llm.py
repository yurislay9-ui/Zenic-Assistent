"""Tests for criticality adjustments and LLM path in business logic agent."""

import pytest
from unittest.mock import MagicMock

from src.core.agents.business_logic_agent import BusinessLogicAgent
from src.core.agents.schemas import BusinessInput, BusinessOutput
from src.core.agents.base import AgentResult


# ============================================================
#  Test: Criticality Adjustments (F4)
# ============================================================

class TestBusinessCriticalityAdjustments:
    """Tests for F4 criticality-aware adjustments on business logic."""

    def test_no_adjustments_by_default(self, agent):
        """Should not modify result when no adjustments set."""
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={"items": [{"quantity": 1, "price": 50.0}]},
        ))
        # No F4 audit entries should be present
        assert not any("F4:" in i for i in result.insights)

    def test_audit_trail_adjustment(self, agent):
        """Should add audit trail when audit_trail is enabled."""
        agent.set_criticality_adjustments({
            "business_agent": {
                "audit_trail": True,
                "validation_layers": 1,
            }
        })
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={"items": [{"quantity": 1, "price": 50.0}]},
        ))
        assert any("audit:" in se for se in result.side_effects)
        assert "_audit" in result.data

    def test_validation_layers_2(self, agent):
        """Should add data integrity insight for validation layers >= 2."""
        agent.set_criticality_adjustments({
            "business_agent": {
                "audit_trail": False,
                "validation_layers": 2,
            }
        })
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={"items": [{"quantity": 1, "price": 50.0}]},
        ))
        assert any("Data integrity check" in i for i in result.insights)

    def test_validation_layers_3_with_rollback(self, agent):
        """Should add rollback and cross-reference insights for level 3."""
        agent.set_criticality_adjustments({
            "business_agent": {
                "audit_trail": False,
                "validation_layers": 3,
                "rollback": True,
            }
        })
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={"items": [{"quantity": 1, "price": 50.0}]},
        ))
        assert any("Cross-reference" in i for i in result.insights)
        assert any("Rollback" in i for i in result.insights)

    def test_idempotency_check(self, agent):
        """Should add idempotency insight when enabled."""
        agent.set_criticality_adjustments({
            "business_agent": {
                "audit_trail": False,
                "validation_layers": 1,
                "idempotency_check": True,
            }
        })
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={"items": [{"quantity": 1, "price": 50.0}]},
        ))
        assert any("Idempotency" in i for i in result.insights)


# ============================================================
#  Test: LLM Path (build_prompt + parse_response)
# ============================================================

class TestBusinessLLMPath:
    """Tests for the LLM prompt building and response parsing."""

    def test_build_prompt_with_business_input(self, agent):
        """Should build system + user prompt from BusinessInput."""
        system, user = agent.build_prompt(BusinessInput(
            operation_type="invoice",
            data={"items": [{"price": 100}]},
            context={"region": "MX"},
            description="Calculate invoice total",
        ))
        assert "business" in system.lower()
        assert "invoice" in user

    def test_build_prompt_with_string(self, agent):
        """Should build prompt from plain string."""
        system, user = agent.build_prompt("simple business operation")
        assert "business" in system.lower()
        assert "custom" in user  # defaults to "custom" op type

    def test_parse_response_valid_json(self, agent):
        """Should parse valid JSON response from LLM."""
        raw = '{"success":true,"data":{"total":116},"side_effects":["calculated"],"insights":["done"],"errors":[]}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.success is True
        assert result.data["total"] == 116
        assert result.source == "llm"

    def test_parse_response_free_text(self, agent):
        """Should parse free text when no JSON is found."""
        raw = "The invoice total is 116.0 with tax applied"
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.success is True
        assert "answer" in result.data

    def test_parse_response_empty_text(self, agent):
        """Should return None for very short/empty text."""
        result = agent.parse_response("short", None)
        assert result is None
