"""Tests for high-level API, wire(), and dependency injection in business logic agent."""

import pytest
from unittest.mock import MagicMock

from src.core.agents.business_logic_agent import BusinessLogicAgent, VALID_OPERATION_TYPES
from src.core.agents.schemas import BusinessInput, BusinessOutput
from src.core.agents.base import AgentResult


# ============================================================
#  Test: High-Level API
# ============================================================

class TestBusinessHighLevelAPI:
    """Tests for execute_business and execute_with_runner."""

    def test_execute_business_direct(self, agent):
        """Should execute business logic directly without LLM."""
        result = agent.execute_business(
            operation_type="invoice",
            data={"items": [{"quantity": 2, "price": 50.0}]},
        )
        assert result.success is True
        assert result.data["subtotal"] == 100.0

    def test_execute_with_runner_success(self, agent):
        """Should use LLM result when runner succeeds."""
        mock_runner = MagicMock()
        llm_output = BusinessOutput(
            success=True,
            data={"total": 200},
            source="llm",
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        result = agent.execute_with_runner(
            mock_runner, "invoice",
            data={"items": [{"quantity": 1, "price": 100.0}]},
        )
        assert result.data["total"] == 200
        assert result.source == "llm"

    def test_execute_with_runner_failure_falls_back(self, agent):
        """Should fall back to deterministic logic when runner fails."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, error="LLM timeout"
        )
        result = agent.execute_with_runner(
            mock_runner, "invoice",
            data={"items": [{"quantity": 1, "price": 100.0}]},
        )
        assert result.success is True
        assert result.source == "fallback"


# ============================================================
#  Test: Wire and Dependencies
# ============================================================

class TestBusinessWireAndDeps:
    """Tests for wire() and dependency injection."""

    def test_wire_semantic_engine(self, agent):
        """Should update semantic engine reference via wire()."""
        mock_se = MagicMock()
        agent.wire(semantic_engine=mock_se)
        assert agent._semantic_engine is mock_se

    def test_wire_smart_memory(self, agent):
        """Should update smart memory reference via wire()."""
        mock_mem = MagicMock()
        agent.wire(smart_memory=mock_mem)
        assert agent._smart_memory is mock_mem

    def test_wire_none_does_not_overwrite(self, agent):
        """Wire with None should not overwrite existing reference."""
        mock_se = MagicMock()
        agent.wire(semantic_engine=mock_se)
        agent.wire(semantic_engine=None)
        assert agent._semantic_engine is mock_se

    def test_valid_operation_types(self):
        """VALID_OPERATION_TYPES should include all expected types."""
        assert "invoice" in VALID_OPERATION_TYPES
        assert "inventory" in VALID_OPERATION_TYPES
        assert "crm" in VALID_OPERATION_TYPES
        assert "custom" in VALID_OPERATION_TYPES

    def test_stats_tracking(self, agent):
        """Should track fallback call statistics."""
        agent.fallback(BusinessInput(
            operation_type="custom", data={"x": 1},
        ))
        stats = agent.stats
        assert stats["name"] == "business_logic"
        assert stats["total_calls"] >= 1
