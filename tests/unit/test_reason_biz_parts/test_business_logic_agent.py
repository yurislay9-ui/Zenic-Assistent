"""
Tests for BusinessLogicAgent fallback, LLM path, and edge cases.
"""

import pytest
from unittest.mock import MagicMock

from src.core.agents.business_logic_agent import BusinessLogicAgent
from src.core.agents.schemas import BusinessInput, BusinessOutput
from src.core.agents.base import AgentResult


# ============================================================
#  BusinessLogicAgent: Fallback Business Logic
# ============================================================

class TestBusinessLogicAgentFallback:
    """Tests for deterministic fallback business logic."""

    def test_invoice_calculation(self):
        """Should calculate invoices correctly."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("invoice", {
            "items": [{"name": "Widget", "quantity": 2, "price": 10.0}],
            "tax_rate": 0.16,
            "discount": 0,
        })
        assert result.success is True
        assert result.data["subtotal"] == 20.0
        assert result.data["tax_amount"] == 3.2
        assert result.data["total"] == 23.2

    def test_invoice_with_discount(self):
        """Should calculate invoices with discount."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("invoice", {
            "items": [{"name": "Widget", "quantity": 1, "price": 100.0}],
            "tax_rate": 0.10,
            "discount": 10,
        })
        assert result.success is True
        assert result.data["subtotal"] == 100.0
        assert result.data["discount_amount"] == 10.0
        assert result.data["tax_amount"] == 9.0
        assert result.data["total"] == 99.0

    def test_invoice_no_items(self):
        """Should fail gracefully when no items provided."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("invoice", {"items": []})
        assert result.success is False
        assert len(result.errors) > 0

    def test_inventory_add(self):
        """Should handle inventory add operation."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("inventory", {
            "product_id": "P001",
            "quantity_change": 5,
            "operation": "add",
            "current_quantity": 10,
        })
        assert result.success is True
        assert result.data["new_quantity"] == 15
        assert result.data["change"] == 5

    def test_inventory_remove(self):
        """Should handle inventory remove operation."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("inventory", {
            "product_id": "P001",
            "quantity_change": 3,
            "operation": "remove",
            "current_quantity": 10,
        })
        assert result.success is True
        assert result.data["new_quantity"] == 7

    def test_inventory_low_stock_alert(self):
        """Should generate low stock alert."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("inventory", {
            "product_id": "P001",
            "quantity_change": 8,
            "operation": "remove",
            "current_quantity": 10,
            "low_stock_threshold": 5,
        })
        assert result.success is True
        assert result.data["new_quantity"] == 2
        assert result.data["low_stock"] is True
        assert len(result.data["alerts"]) > 0

    def test_crm_advance_stage(self):
        """Should advance CRM pipeline stage."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("crm", {
            "current_stage": "new",
            "action": "advance",
        })
        assert result.success is True
        assert result.data["new_stage"] == "contacted"
        assert result.data["probability"] == 0.20

    def test_crm_close_won(self):
        """Should close CRM lead as won."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("crm", {
            "current_stage": "negotiation",
            "action": "close_won",
        })
        assert result.success is True
        assert result.data["new_stage"] == "closed_won"
        assert result.data["probability"] == 1.0

    def test_task_scheduling(self):
        """Should schedule and assign tasks."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("task", {
            "tasks": [
                {"name": "Fix bug", "priority": "critical"},
                {"name": "Add feature", "priority": "medium"},
            ],
            "resources": [{"name": "Alice"}, {"name": "Bob"}],
        })
        assert result.success is True
        assert result.data["total_tasks"] == 2
        assert len(result.data["assignments"]) == 2
        assert result.data["schedule"][0]["task"] == "Fix bug"

    def test_notification_dispatch(self):
        """Should dispatch notifications."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("notification", {
            "channel": "email",
            "recipients": "alice@test.com, bob@test.com",
            "message": "Hello!",
        })
        assert result.success is True
        assert result.data["channel"] == "email"
        assert len(result.data["recipients"]) == 2

    def test_analytics(self):
        """Should compute analytics."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("analytics", {
            "data": [
                {"name": "A", "value": 10},
                {"name": "B", "value": 20},
                {"name": "C", "value": 30},
            ],
        })
        assert result.success is True
        assert result.data["record_count"] == 3
        assert "value" in result.data["numeric_fields"]
        assert result.data["numeric_fields"]["value"]["avg"] == 20.0

    def test_report_generation(self):
        """Should generate reports."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("report", {
            "title": "Sales Report",
            "data": [{"id": 1}, {"id": 2}],
        })
        assert result.success is True
        assert result.data["title"] == "Sales Report"
        assert result.data["record_count"] == 2

    def test_custom_operation(self):
        """Should handle custom operations."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("custom", {
            "field1": "value1",
            "field2": 42,
        })
        assert result.success is True
        assert result.data["processed"] is True


class TestBusinessLogicAgentLLMPath:
    """Tests for LLM prompt building and response parsing."""

    def test_build_prompt(self):
        """Should build business logic prompt."""
        agent = BusinessLogicAgent()
        system, user = agent.build_prompt(BusinessInput(
            operation_type="invoice",
            data={"items": [{"name": "Widget", "quantity": 1, "price": 10}]},
            description="Calculate invoice total",
        ))
        assert "business logic" in system.lower()
        assert "invoice" in user.lower()

    def test_parse_json_response(self):
        """Should parse valid JSON business response."""
        agent = BusinessLogicAgent()
        raw = '{"success":true,"data":{"total":23.2},"side_effects":["invoice_calculated"],"insights":["Total calculated"],"errors":[]}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.success is True
        assert result.data["total"] == 23.2
        assert result.source == "llm"

    def test_parse_free_text(self):
        """Should parse free text business response."""
        agent = BusinessLogicAgent()
        raw = "The invoice total is 23.20 including tax."
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.source == "llm"

    def test_execute_with_runner_llm(self):
        """Should use LLM result when runner succeeds."""
        agent = BusinessLogicAgent()
        mock_runner = MagicMock()
        llm_output = BusinessOutput(
            success=True, data={"total": 50.0}, source="llm"
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        result = agent.execute_with_runner(mock_runner, "invoice", {"items": []})
        assert result.source == "llm"

    def test_execute_with_runner_fallback(self):
        """Should fallback when runner fails."""
        agent = BusinessLogicAgent()
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, source="error"
        )
        result = agent.execute_with_runner(
            mock_runner, "invoice",
            {"items": [{"name": "X", "quantity": 1, "price": 10}]},
        )
        assert result.source == "fallback"
        assert result.success is True


class TestBusinessLogicAgentEdgeCases:
    """Edge case tests for BusinessLogicAgent."""

    def test_invalid_operation_type(self):
        """Should use custom handler for unknown types."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("unknown_type", {"data": "test"})
        assert result.success is True

    def test_stats_tracking(self):
        """Should track stats after operations."""
        agent = BusinessLogicAgent()
        agent.execute_business("custom", {"field": "value"})
        stats = agent.stats
        assert stats["name"] == "business_logic"
        assert stats["total_calls"] >= 1

    def test_wire_dependencies(self):
        """Should accept dependencies via wire()."""
        agent = BusinessLogicAgent()
        mock_sem = MagicMock()
        mock_mem = MagicMock()
        agent.wire(semantic_engine=mock_sem, smart_memory=mock_mem)
        assert agent._semantic_engine is mock_sem
        assert agent._smart_memory is mock_mem

    def test_inventory_zero_stock(self):
        """Should handle zero stock correctly."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("inventory", {
            "product_id": "P001",
            "quantity_change": 10,
            "operation": "remove",
            "current_quantity": 5,
        })
        assert result.data["new_quantity"] == 0
        assert any(a["type"] == "out_of_stock" for a in result.data["alerts"])
