"""
ZENIC-AGENTS — Chain template rendering and instantiation.

Contains the built-in template definitions and the logic to instantiate
a concrete ComposedChain from a template with variable substitution.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from ._types import (
    ChainTemplate,
    TemplateCategory,
    TemplateStep,
    TemplateVariable,
    _substitute_value,
    logger,
)


# ---------------------------------------------------------------------------
#  Built-in template definitions
# ---------------------------------------------------------------------------


def get_builtin_definitions() -> list[ChainTemplate]:
    """Return the five built-in template definitions."""
    now = time.time()
    return [
        # ── 1. detect_validate_notify ──────────────────────────────
        ChainTemplate(
            template_id="builtin_detect_validate_notify",
            name="Detect, Validate & Notify",
            description="Event detected → validate data → send notification",
            category=TemplateCategory.MONITOR_DETECT.value,
            event_patterns=["stock_low", "threshold_exceeded", "anomaly_detected", "alert_triggered"],
            intent_keywords=["detect", "validate", "notify", "alert", "monitor"],
            steps=[
                TemplateStep(
                    step_type="trigger",
                    config_template={
                        "event_type": "{{event_type}}",
                        "source": "{{source}}",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=10000,
                ),
                TemplateStep(
                    step_type="condition",
                    config_template={
                        "validation_rules": "{{validation_rules}}",
                        "check_type": "data_validation",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=15000,
                ),
                TemplateStep(
                    step_type="notification",
                    config_template={
                        "channel": "{{notification_channel}}",
                        "recipient": "{{recipient}}",
                        "message_template": "Event {{event_type}} detected and validated",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=10000,
                ),
            ],
            variables=[
                TemplateVariable("event_type", "str", None, True, "Type of event to detect"),
                TemplateVariable("source", "str", "system", False, "Event source identifier"),
                TemplateVariable("validation_rules", "list", [], False, "Validation rules to apply"),
                TemplateVariable("notification_channel", "str", "email", False, "Notification channel"),
                TemplateVariable("recipient", "str", None, True, "Notification recipient"),
            ],
            version="1.0.0",
            created_at=now,
        ),
        # ── 2. detect_validate_create_task_escalate ────────────────
        ChainTemplate(
            template_id="builtin_detect_validate_create_task_escalate",
            name="Detect, Validate, Create Task & Escalate",
            description="Event detected → validate → create task → escalate if unresolved",
            category=TemplateCategory.INCIDENT_RESPONSE.value,
            event_patterns=["incident", "error_spike", "service_down", "outage"],
            intent_keywords=["incident", "escalate", "task", "resolve", "response"],
            steps=[
                TemplateStep(
                    step_type="trigger",
                    config_template={
                        "event_type": "{{event_type}}",
                        "severity": "{{severity}}",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=10000,
                ),
                TemplateStep(
                    step_type="condition",
                    config_template={
                        "validation_rules": "{{validation_rules}}",
                        "check_type": "incident_validation",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=15000,
                ),
                TemplateStep(
                    step_type="action",
                    config_template={
                        "action_type": "create_task",
                        "title": "Incident: {{event_type}}",
                        "priority": "{{severity}}",
                        "assignee": "{{default_assignee}}",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=20000,
                ),
                TemplateStep(
                    step_type="condition",
                    config_template={
                        "check_type": "resolution_check",
                        "timeout_minutes": "{{escalation_timeout_minutes}}",
                    },
                    next_step_id="",
                    condition_expr="context.resolved == false",
                    timeout_ms=30000,
                ),
                TemplateStep(
                    step_type="notification",
                    config_template={
                        "channel": "email",
                        "recipient": "{{escalation_recipient}}",
                        "message_template": "Unresolved incident {{event_type}} escalated",
                        "priority": "high",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=10000,
                ),
            ],
            variables=[
                TemplateVariable("event_type", "str", None, True, "Incident event type"),
                TemplateVariable("severity", "str", "medium", False, "Incident severity level"),
                TemplateVariable("validation_rules", "list", [], False, "Validation rules"),
                TemplateVariable("default_assignee", "str", "oncall", False, "Default task assignee"),
                TemplateVariable("escalation_timeout_minutes", "int", 30, False, "Minutes before escalation"),
                TemplateVariable("escalation_recipient", "str", None, True, "Escalation recipient"),
            ],
            version="1.0.0",
            created_at=now,
        ),
        # ── 3. low_stock_chain ─────────────────────────────────────
        ChainTemplate(
            template_id="builtin_low_stock_chain",
            name="Low Stock Response Chain",
            description="Stock below threshold → check alternatives → notify procurement → create reorder",
            category=TemplateCategory.MONITOR_DETECT.value,
            event_patterns=["stock_low", "inventory_depleted", "reorder_point"],
            intent_keywords=["stock", "inventory", "reorder", "procurement", "supply"],
            steps=[
                TemplateStep(
                    step_type="trigger",
                    config_template={
                        "event_type": "stock_low",
                        "product_id": "{{product_id}}",
                        "current_stock": "{{current_stock}}",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=10000,
                ),
                TemplateStep(
                    step_type="condition",
                    config_template={
                        "check_type": "alternative_check",
                        "product_id": "{{product_id}}",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=15000,
                ),
                TemplateStep(
                    step_type="notification",
                    config_template={
                        "channel": "{{notification_channel}}",
                        "recipient": "{{procurement_contact}}",
                        "message_template": "Low stock alert for product {{product_id}}: {{current_stock}} units",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=10000,
                ),
                TemplateStep(
                    step_type="action",
                    config_template={
                        "action_type": "create_reorder",
                        "product_id": "{{product_id}}",
                        "quantity": "{{reorder_quantity}}",
                        "supplier": "{{preferred_supplier}}",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=20000,
                ),
            ],
            variables=[
                TemplateVariable("product_id", "str", None, True, "Product identifier"),
                TemplateVariable("current_stock", "int", 0, True, "Current stock level"),
                TemplateVariable("notification_channel", "str", "email", False, "Notification channel"),
                TemplateVariable("procurement_contact", "str", None, True, "Procurement team contact"),
                TemplateVariable("reorder_quantity", "int", 100, False, "Quantity to reorder"),
                TemplateVariable("preferred_supplier", "str", "default", False, "Preferred supplier name"),
            ],
            version="1.0.0",
            created_at=now,
        ),
        # ── 4. invoice_overdue_chain ───────────────────────────────
        ChainTemplate(
            template_id="builtin_invoice_overdue_chain",
            name="Invoice Overdue Response Chain",
            description="Invoice overdue → send reminder → escalate to manager → generate report",
            category=TemplateCategory.NOTIFICATION_ESCALATE.value,
            event_patterns=["invoice_overdue", "payment_late", "payment_overdue"],
            intent_keywords=["invoice", "overdue", "payment", "reminder", "escalate"],
            steps=[
                TemplateStep(
                    step_type="trigger",
                    config_template={
                        "event_type": "invoice_overdue",
                        "invoice_id": "{{invoice_id}}",
                        "amount": "{{amount}}",
                        "days_overdue": "{{days_overdue}}",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=10000,
                ),
                TemplateStep(
                    step_type="notification",
                    config_template={
                        "channel": "email",
                        "recipient": "{{customer_email}}",
                        "message_template": "Reminder: Invoice {{invoice_id}} for {{amount}} is {{days_overdue}} days overdue",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=10000,
                ),
                TemplateStep(
                    step_type="condition",
                    config_template={
                        "check_type": "payment_check",
                        "invoice_id": "{{invoice_id}}",
                    },
                    next_step_id="",
                    condition_expr="context.amount > 10000",
                    timeout_ms=15000,
                ),
                TemplateStep(
                    step_type="notification",
                    config_template={
                        "channel": "email",
                        "recipient": "{{manager_email}}",
                        "message_template": "ESCALATION: Invoice {{invoice_id}} amount {{amount}} overdue {{days_overdue}} days",
                        "priority": "high",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=10000,
                ),
                TemplateStep(
                    step_type="action",
                    config_template={
                        "action_type": "generate_report",
                        "report_type": "overdue_invoice",
                        "invoice_id": "{{invoice_id}}",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=20000,
                ),
            ],
            variables=[
                TemplateVariable("invoice_id", "str", None, True, "Invoice identifier"),
                TemplateVariable("amount", "float", 0.0, True, "Invoice amount"),
                TemplateVariable("days_overdue", "int", 0, True, "Days overdue"),
                TemplateVariable("customer_email", "str", None, True, "Customer email address"),
                TemplateVariable("manager_email", "str", None, True, "Manager email for escalation"),
            ],
            version="1.0.0",
            created_at=now,
        ),
        # ── 5. data_import_chain ───────────────────────────────────
        ChainTemplate(
            template_id="builtin_data_import_chain",
            name="Data Import Pipeline",
            description="File received → validate schema → import to DB → notify completion",
            category=TemplateCategory.DATA_PIPELINE.value,
            event_patterns=["file_received", "file_uploaded", "data_received"],
            intent_keywords=["import", "data", "file", "pipeline", "etl", "ingest"],
            steps=[
                TemplateStep(
                    step_type="trigger",
                    config_template={
                        "event_type": "file_received",
                        "file_path": "{{file_path}}",
                        "file_format": "{{file_format}}",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=10000,
                ),
                TemplateStep(
                    step_type="condition",
                    config_template={
                        "check_type": "schema_validation",
                        "expected_schema": "{{expected_schema}}",
                        "file_format": "{{file_format}}",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=30000,
                ),
                TemplateStep(
                    step_type="action",
                    config_template={
                        "action_type": "database_operation",
                        "operation": "import",
                        "target_table": "{{target_table}}",
                        "file_path": "{{file_path}}",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=60000,
                ),
                TemplateStep(
                    step_type="notification",
                    config_template={
                        "channel": "{{notification_channel}}",
                        "recipient": "{{recipient}}",
                        "message_template": "Data import completed for {{file_path}} into {{target_table}}",
                    },
                    next_step_id="",
                    condition_expr="",
                    timeout_ms=10000,
                ),
            ],
            variables=[
                TemplateVariable("file_path", "str", None, True, "Path to the data file"),
                TemplateVariable("file_format", "str", "csv", False, "File format (csv, json, xml)"),
                TemplateVariable("expected_schema", "list", [], False, "Expected schema definition"),
                TemplateVariable("target_table", "str", None, True, "Target database table"),
                TemplateVariable("notification_channel", "str", "email", False, "Notification channel"),
                TemplateVariable("recipient", "str", None, True, "Notification recipient"),
            ],
            version="1.0.0",
            created_at=now,
        ),
    ]


# ---------------------------------------------------------------------------
#  Instantiation
# ---------------------------------------------------------------------------


def instantiate_template(
    template_id: str,
    template: ChainTemplate,
    variables: dict[str, Any],
) -> "ComposedChain":
    """Create a concrete ComposedChain from a template with variable substitution.

    Args:
        template_id: The template identifier (used for logging / keying).
        template: The ChainTemplate to instantiate.
        variables: User-supplied variable overrides.

    Returns:
        A fully-resolved ComposedChain ready for execution.

    Raises:
        ValueError: If a required variable is missing.
    """
    # Import here to avoid circular imports at module level
    from ..chain_composer import (
        ChainStep,
        ChainStepType,
        ChainStatus,
        ComposedChain,
    )

    # Merge defaults and validate required variables
    resolved_vars: dict[str, Any] = {}
    for var in template.variables:
        if var.name in variables:
            resolved_vars[var.name] = variables[var.name]
        elif var.default_value is not None:
            resolved_vars[var.name] = var.default_value
        elif var.required:
            raise ValueError(
                f"Required variable '{var.name}' not provided for template '{template_id}'"
            )
        # optional and no default — skip

    # Apply variable substitution to step configs
    chain_steps: list[ChainStep] = []
    for idx, tpl_step in enumerate(template.steps):
        substituted_config = _substitute_value(tpl_step.config_template, resolved_vars)

        # Resolve step_type enum
        step_type_str = tpl_step.step_type
        try:
            step_type = ChainStepType(step_type_str)
        except ValueError:
            step_type = ChainStepType.ACTION

        chain_step = ChainStep(
            step_id=f"{template_id}_step_{idx}",
            step_type=step_type,
            config=substituted_config,
            next_step_id=tpl_step.next_step_id,
            condition_expr=tpl_step.condition_expr,
            timeout_ms=tpl_step.timeout_ms,
        )
        chain_steps.append(chain_step)

    # Link sequential steps that don't have explicit next_step_id
    for i in range(len(chain_steps) - 1):
        if not chain_steps[i].next_step_id:
            chain_steps[i].next_step_id = chain_steps[i + 1].step_id

    chain_id = f"chain_{uuid.uuid4().hex[:12]}"
    composed = ComposedChain(
        chain_id=chain_id,
        name=template.name,
        description=template.description,
        steps=chain_steps,
        metadata={
            "source_template": template_id,
            "template_version": template.version,
            "category": template.category,
            "resolved_variables": list(resolved_vars.keys()),
        },
        tenant_id="",
        created_at=time.time(),
        status=ChainStatus.READY,
    )

    logger.info(
        "Instantiated chain %s from template %s with %d steps",
        chain_id, template_id, len(chain_steps),
    )
    return composed
