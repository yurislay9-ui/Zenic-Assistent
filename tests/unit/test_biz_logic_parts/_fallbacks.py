"""Tests for business logic fallback operations: invoice, inventory, CRM, task, report/notification/analytics/custom."""

import pytest

from src.core.agents.business_logic_agent import BusinessLogicAgent
from src.core.agents.schemas import BusinessInput


# ============================================================
#  Test: Invoice Fallback
# ============================================================

class TestBusinessInvoiceFallback:
    """Tests for invoice calculation fallback logic."""

    def test_invoice_basic_calculation(self, agent):
        """Should calculate subtotal, tax, discount, and total."""
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={
                "items": [
                    {"name": "Widget", "quantity": 2, "price": 50.0},
                    {"name": "Gadget", "quantity": 1, "price": 100.0},
                ],
                "tax_rate": 0.16,
                "discount": 10,
            },
        ))
        assert result.success is True
        assert result.data["subtotal"] == 200.0
        assert result.data["discount_amount"] == 20.0
        assert result.data["tax_amount"] == 28.8
        assert result.data["total"] == 208.8
        assert result.data["item_count"] == 2
        assert result.source == "fallback"

    def test_invoice_no_discount(self, agent):
        """Should handle zero discount."""
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={
                "items": [{"name": "A", "quantity": 1, "price": 100.0}],
                "tax_rate": 0.16,
            },
        ))
        assert result.success is True
        assert result.data["discount_amount"] == 0.0
        assert result.data["discount_pct"] == 0

    def test_invoice_no_items(self, agent):
        """Should fail when no items provided."""
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={"items": []},
        ))
        assert result.success is False
        assert "No items" in result.errors[0]

    def test_invoice_default_tax_rate(self, agent):
        """Should use 0.16 as default tax rate."""
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={"items": [{"quantity": 1, "price": 100.0}]},
        ))
        assert result.success is True
        assert result.data["tax_rate"] == 0.16


# ============================================================
#  Test: Inventory Fallback
# ============================================================

class TestBusinessInventoryFallback:
    """Tests for inventory tracking fallback logic."""

    def test_inventory_add_stock(self, agent):
        """Should add stock correctly."""
        result = agent.fallback(BusinessInput(
            operation_type="inventory",
            data={
                "product_id": "P001",
                "quantity_change": 10,
                "operation": "add",
                "current_quantity": 5,
            },
        ))
        assert result.success is True
        assert result.data["new_quantity"] == 15
        assert result.data["previous_quantity"] == 5

    def test_inventory_remove_stock(self, agent):
        """Should remove stock and not go below zero."""
        result = agent.fallback(BusinessInput(
            operation_type="inventory",
            data={
                "product_id": "P001",
                "quantity_change": 20,
                "operation": "remove",
                "current_quantity": 15,
            },
        ))
        assert result.success is True
        assert result.data["new_quantity"] == 0
        assert any(a["type"] == "out_of_stock" for a in result.data["alerts"])

    def test_inventory_low_stock_alert(self, agent):
        """Should trigger low stock alert when below threshold."""
        result = agent.fallback(BusinessInput(
            operation_type="inventory",
            data={
                "product_id": "P002",
                "quantity_change": 8,
                "operation": "remove",
                "current_quantity": 15,
                "low_stock_threshold": 10,
            },
        ))
        assert result.data["low_stock"] is True
        assert any(a["type"] == "low_stock" for a in result.data["alerts"])

    def test_inventory_set_stock(self, agent):
        """Should set stock to exact value."""
        result = agent.fallback(BusinessInput(
            operation_type="inventory",
            data={
                "product_id": "P003",
                "quantity_change": 50,
                "operation": "set",
                "current_quantity": 30,
            },
        ))
        assert result.data["new_quantity"] == 50


# ============================================================
#  Test: CRM Fallback
# ============================================================

class TestBusinessCRMFallback:
    """Tests for CRM pipeline fallback logic."""

    def test_crm_advance_stage(self, agent):
        """Should advance lead to next stage."""
        result = agent.fallback(BusinessInput(
            operation_type="crm",
            data={
                "lead_data": {"name": "Acme Corp"},
                "current_stage": "new",
                "action": "advance",
            },
        ))
        assert result.success is True
        assert result.data["new_stage"] == "contacted"
        assert result.data["previous_stage"] == "new"

    def test_crm_close_won(self, agent):
        """Should move lead to closed_won stage."""
        result = agent.fallback(BusinessInput(
            operation_type="crm",
            data={
                "lead_data": {"name": "Big Corp"},
                "current_stage": "negotiation",
                "action": "close_won",
            },
        ))
        assert result.data["new_stage"] == "closed_won"
        assert result.data["probability"] == 1.0
        assert "Send onboarding" in result.data["next_action"]

    def test_crm_close_lost(self, agent):
        """Should move lead to closed_lost stage."""
        result = agent.fallback(BusinessInput(
            operation_type="crm",
            data={
                "current_stage": "proposal",
                "action": "close_lost",
            },
        ))
        assert result.data["new_stage"] == "closed_lost"
        assert result.data["probability"] == 0.0

    def test_crm_regress_stage(self, agent):
        """Should regress lead to previous stage."""
        result = agent.fallback(BusinessInput(
            operation_type="crm",
            data={
                "current_stage": "proposal",
                "action": "regress",
            },
        ))
        assert result.data["new_stage"] == "qualified"


# ============================================================
#  Test: Task Fallback
# ============================================================

class TestBusinessTaskFallback:
    """Tests for task scheduling fallback logic."""

    def test_task_prioritization(self, agent):
        """Should sort tasks by priority score."""
        result = agent.fallback(BusinessInput(
            operation_type="task",
            data={
                "tasks": [
                    {"name": "Low task", "priority": "low"},
                    {"name": "Critical task", "priority": "critical"},
                    {"name": "Medium task", "priority": "medium"},
                ],
            },
        ))
        assert result.success is True
        schedule = result.data["schedule"]
        assert schedule[0]["task"] == "Critical task"
        assert schedule[-1]["task"] == "Low task"

    def test_task_assignment(self, agent):
        """Should assign tasks to resources round-robin."""
        result = agent.fallback(BusinessInput(
            operation_type="task",
            data={
                "tasks": [
                    {"name": "Task A", "priority": "high"},
                    {"name": "Task B", "priority": "medium"},
                ],
                "resources": [
                    {"name": "Alice"},
                    {"name": "Bob"},
                ],
            },
        ))
        assignments = result.data["assignments"]
        assert len(assignments) == 2
        assert assignments[0]["assigned_to"] == "Alice"
        assert assignments[1]["assigned_to"] == "Bob"

    def test_task_no_tasks(self, agent):
        """Should fail when no tasks provided."""
        result = agent.fallback(BusinessInput(
            operation_type="task",
            data={"tasks": []},
        ))
        assert result.success is False
        assert "No tasks" in result.errors[0]


# ============================================================
#  Test: Report / Notification / Analytics / Custom Fallbacks
# ============================================================

class TestBusinessOtherFallbacks:
    """Tests for report, notification, analytics, and custom fallbacks."""

    def test_report_generation_list(self, agent):
        """Should generate a report summary from list data."""
        result = agent.fallback(BusinessInput(
            operation_type="report",
            data={
                "data": [{"id": 1}, {"id": 2}],
                "title": "Sales Report",
            },
        ))
        assert result.success is True
        assert result.data["title"] == "Sales Report"
        assert result.data["record_count"] == 2

    def test_notification_dispatch(self, agent):
        """Should dispatch a notification."""
        result = agent.fallback(BusinessInput(
            operation_type="notification",
            data={
                "channel": "email",
                "recipients": ["user@example.com"],
                "message": "Hello!",
            },
        ))
        assert result.success is True
        assert result.data["channel"] == "email"
        assert result.data["dispatched"] is True

    def test_notification_string_recipients(self, agent):
        """Should handle comma-separated string recipients."""
        result = agent.fallback(BusinessInput(
            operation_type="notification",
            data={
                "recipients": "a@x.com, b@x.com",
            },
        ))
        assert len(result.data["recipients"]) == 2

    def test_analytics_basic(self, agent):
        """Should compute basic analytics from data."""
        result = agent.fallback(BusinessInput(
            operation_type="analytics",
            data={
                "data": [
                    {"age": 25, "salary": 50000},
                    {"age": 35, "salary": 70000},
                    {"age": 45, "salary": 90000},
                ],
            },
        ))
        assert result.success is True
        assert result.data["record_count"] == 3
        assert "age" in result.data["numeric_fields"]
        assert "salary" in result.data["numeric_fields"]

    def test_custom_operation(self, agent):
        """Should pass through custom data with processed flag."""
        result = agent.fallback(BusinessInput(
            operation_type="custom",
            data={"key1": "value1", "_internal": "hidden"},
        ))
        assert result.success is True
        assert result.data["processed"] is True
        assert "key1" in result.data
        assert "_internal" not in result.data
