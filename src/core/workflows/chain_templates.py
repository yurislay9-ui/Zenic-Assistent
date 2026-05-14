"""
ZENIC-AGENTS — ChainTemplateLibrary: Reusable workflow templates.

Manages a library of chain templates that can be instantiated with
variable substitution to produce concrete ComposedChain instances.

Built-in templates cover common PYME workflows:
  1. detect_validate_notify
  2. detect_validate_create_task_escalate
  3. low_stock_chain
  4. invoice_overdue_chain
  5. data_import_chain

Thread-safe via RLock. Persisted to SQLite (chain_templates.sqlite).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Persistence paths
# ---------------------------------------------------------------------------

_DB_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "db")
_DB_PATH = os.path.join(_DB_DIR, "chain_templates.sqlite")

# ---------------------------------------------------------------------------
#  Enums
# ---------------------------------------------------------------------------


class TemplateCategory(str, Enum):
    """Categories for chain templates."""

    MONITOR_DETECT = "monitor_detect"
    INCIDENT_RESPONSE = "incident_response"
    NOTIFICATION_ESCALATE = "notification_escalate"
    DATA_PIPELINE = "data_pipeline"
    COMPLIANCE = "compliance"


# ---------------------------------------------------------------------------
#  Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TemplateVariable:
    """A variable placeholder in a template."""

    name: str
    var_type: str = "str"  # str, int, float, bool, list
    default_value: Any = None
    required: bool = True
    description: str = ""


@dataclass
class TemplateStep:
    """A single step within a chain template."""

    step_type: str  # trigger, condition, action, notification, delay, sub_chain
    config_template: dict[str, Any] = field(default_factory=dict)
    next_step_id: str = ""
    condition_expr: str = ""
    timeout_ms: int = 30000


@dataclass
class ChainTemplate:
    """A reusable workflow template with variable placeholders."""

    template_id: str = ""
    name: str = ""
    description: str = ""
    category: str = TemplateCategory.MONITOR_DETECT.value
    event_patterns: list[str] = field(default_factory=list)
    intent_keywords: list[str] = field(default_factory=list)
    steps: list[TemplateStep] = field(default_factory=list)
    variables: list[TemplateVariable] = field(default_factory=list)
    version: str = "1.0.0"
    created_at: float = 0.0


# ---------------------------------------------------------------------------
#  Variable substitution
# ---------------------------------------------------------------------------


def _substitute_value(value: Any, variables: dict[str, Any]) -> Any:
    """Recursively substitute {{variable}} placeholders in a value."""
    if isinstance(value, str):
        # Check if the entire string is a single placeholder
        if value.startswith("{{") and value.endswith("}}") and value.count("{{") == 1:
            var_name = value[2:-2].strip()
            if var_name in variables:
                return variables[var_name]
            return value
        # Substitute multiple placeholders within a string
        result = value
        for var_name, var_value in variables.items():
            placeholder = "{{" + var_name + "}}"
            if placeholder in result:
                result = result.replace(placeholder, str(var_value))
        return result
    if isinstance(value, dict):
        return {k: _substitute_value(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_value(item, variables) for item in value]
    return value


# ---------------------------------------------------------------------------
#  ChainTemplateLibrary
# ---------------------------------------------------------------------------


class ChainTemplateLibrary:
    """Library of reusable workflow templates with SQLite persistence.

    Thread-safe via RLock. Singleton via get_template_library().
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._templates: dict[str, ChainTemplate] = {}
        os.makedirs(_DB_DIR, exist_ok=True)
        self._init_db()
        self._load_templates()
        self._register_builtins()
        logger.info("ChainTemplateLibrary initialized with %d templates", len(self._templates))

    # ------------------------------------------------------------------
    #  Database
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create the templates table if it does not exist."""
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chain_templates (
                    template_id  TEXT PRIMARY KEY,
                    name         TEXT NOT NULL,
                    description  TEXT NOT NULL DEFAULT '',
                    category     TEXT NOT NULL DEFAULT 'monitor_detect',
                    event_patterns TEXT NOT NULL DEFAULT '[]',
                    intent_keywords TEXT NOT NULL DEFAULT '[]',
                    steps        TEXT NOT NULL DEFAULT '[]',
                    variables    TEXT NOT NULL DEFAULT '[]',
                    version      TEXT NOT NULL DEFAULT '1.0.0',
                    created_at   REAL NOT NULL DEFAULT 0.0,
                    is_builtin   INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()

    def _load_templates(self) -> None:
        """Load persisted templates from SQLite."""
        with sqlite3.connect(_DB_PATH) as conn:
            rows = conn.execute(
                "SELECT template_id, name, description, category, "
                "event_patterns, intent_keywords, steps, variables, "
                "version, created_at FROM chain_templates"
            ).fetchall()

        for row in rows:
            template_id = row[0]
            try:
                template = ChainTemplate(
                    template_id=template_id,
                    name=row[1],
                    description=row[2],
                    category=row[3],
                    event_patterns=json.loads(row[4]) if row[4] else [],
                    intent_keywords=json.loads(row[5]) if row[5] else [],
                    steps=self._deserialize_steps(json.loads(row[6]) if row[6] else []),
                    variables=self._deserialize_variables(json.loads(row[7]) if row[7] else []),
                    version=row[8],
                    created_at=row[9],
                )
                self._templates[template_id] = template
            except (json.JSONDecodeError, TypeError, KeyError) as exc:
                logger.warning("Failed to load template %s: %s", template_id, exc)

    @staticmethod
    def _serialize_steps(steps: list[TemplateStep]) -> str:
        return json.dumps([
            {
                "step_type": s.step_type,
                "config_template": s.config_template,
                "next_step_id": s.next_step_id,
                "condition_expr": s.condition_expr,
                "timeout_ms": s.timeout_ms,
            }
            for s in steps
        ])

    @staticmethod
    def _deserialize_steps(raw: list[dict[str, Any]]) -> list[TemplateStep]:
        return [
            TemplateStep(
                step_type=s.get("step_type", "action"),
                config_template=s.get("config_template", {}),
                next_step_id=s.get("next_step_id", ""),
                condition_expr=s.get("condition_expr", ""),
                timeout_ms=s.get("timeout_ms", 30000),
            )
            for s in raw
        ]

    @staticmethod
    def _serialize_variables(variables: list[TemplateVariable]) -> str:
        return json.dumps([
            {
                "name": v.name,
                "var_type": v.var_type,
                "default_value": v.default_value,
                "required": v.required,
                "description": v.description,
            }
            for v in variables
        ])

    @staticmethod
    def _deserialize_variables(raw: list[dict[str, Any]]) -> list[TemplateVariable]:
        return [
            TemplateVariable(
                name=v.get("name", ""),
                var_type=v.get("var_type", "str"),
                default_value=v.get("default_value"),
                required=v.get("required", True),
                description=v.get("description", ""),
            )
            for v in raw
        ]

    def _save_template(self, template: ChainTemplate, is_builtin: bool = False) -> None:
        """Persist a single template to SQLite."""
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO chain_templates
                    (template_id, name, description, category,
                     event_patterns, intent_keywords, steps, variables,
                     version, created_at, is_builtin)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    template.template_id,
                    template.name,
                    template.description,
                    template.category,
                    json.dumps(template.event_patterns),
                    json.dumps(template.intent_keywords),
                    self._serialize_steps(template.steps),
                    self._serialize_variables(template.variables),
                    template.version,
                    template.created_at,
                    1 if is_builtin else 0,
                ),
            )
            conn.commit()

    # ------------------------------------------------------------------
    #  CRUD
    # ------------------------------------------------------------------

    def register_template(self, template: ChainTemplate) -> str:
        """Register a new template. Returns the template_id.

        If template.template_id is empty, a UUID is generated.
        """
        with self._lock:
            if not template.template_id:
                template.template_id = f"tpl_{uuid.uuid4().hex[:12]}"
            if not template.created_at:
                template.created_at = time.time()
            self._templates[template.template_id] = template
            self._save_template(template)
            logger.info("Registered template %s: %s", template.template_id, template.name)
            return template.template_id

    def unregister_template(self, template_id: str) -> bool:
        """Remove a template by ID. Returns True if found and removed."""
        with self._lock:
            if template_id not in self._templates:
                logger.warning("Template %s not found for removal", template_id)
                return False
            del self._templates[template_id]
            with sqlite3.connect(_DB_PATH) as conn:
                conn.execute("DELETE FROM chain_templates WHERE template_id=?", (template_id,))
                conn.commit()
            logger.info("Unregistered template %s", template_id)
            return True

    def get_template(self, template_id: str) -> ChainTemplate | None:
        """Retrieve a template by ID."""
        with self._lock:
            return self._templates.get(template_id)

    def list_templates(self, category: str | None = None) -> list[ChainTemplate]:
        """List all templates, optionally filtered by category."""
        with self._lock:
            templates = list(self._templates.values())
        if category is not None:
            templates = [t for t in templates if t.category == category]
        return sorted(templates, key=lambda t: t.name)

    # ------------------------------------------------------------------
    #  Search
    # ------------------------------------------------------------------

    def find_templates_for_event(self, event_type: str) -> list[ChainTemplate]:
        """Find templates whose event_patterns match the given event_type.

        Matching is case-insensitive substring: if the event_type contains
        any of the template's event_patterns (or vice-versa), it matches.
        """
        with self._lock:
            results: list[ChainTemplate] = []
            event_lower = event_type.lower()
            for template in self._templates.values():
                for pattern in template.event_patterns:
                    if pattern.lower() in event_lower or event_lower in pattern.lower():
                        results.append(template)
                        break
            return sorted(results, key=lambda t: t.name)

    def find_templates_for_intent(self, intent: str) -> list[ChainTemplate]:
        """Find templates by keyword matching against intent_keywords.

        A template matches if any of its intent_keywords appear in the
        intent string (case-insensitive).
        """
        with self._lock:
            results: list[ChainTemplate] = []
            intent_lower = intent.lower()
            for template in self._templates.values():
                for keyword in template.intent_keywords:
                    if keyword.lower() in intent_lower:
                        results.append(template)
                        break
            return sorted(results, key=lambda t: len(t.intent_keywords), reverse=True)

    # ------------------------------------------------------------------
    #  Instantiation
    # ------------------------------------------------------------------

    def instantiate(self, template_id: str, variables: dict[str, Any]) -> "ComposedChain":
        """Create a concrete ComposedChain from a template with variable substitution.

        Raises KeyError if the template does not exist.
        Raises ValueError if a required variable is missing.
        """
        # Import here to avoid circular imports at module level
        from .chain_composer import (
            ChainStep,
            ChainStepType,
            ChainStatus,
            ComposedChain,
        )

        with self._lock:
            template = self._templates.get(template_id)
            if template is None:
                raise KeyError(f"Template '{template_id}' not found")

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

    # ------------------------------------------------------------------
    #  Built-in templates
    # ------------------------------------------------------------------

    def _register_builtins(self) -> None:
        """Register the five built-in templates if not already present."""
        builtins = self._builtin_definitions()
        for btpl in builtins:
            if btpl.template_id not in self._templates:
                self._templates[btpl.template_id] = btpl
                self._save_template(btpl, is_builtin=True)
            # else: already loaded from DB

    @staticmethod
    def _builtin_definitions() -> list[ChainTemplate]:
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
#  Singleton
# ---------------------------------------------------------------------------

_instance: ChainTemplateLibrary | None = None
_instance_lock = threading.Lock()


def get_template_library() -> ChainTemplateLibrary:
    """Return the ChainTemplateLibrary singleton (thread-safe)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ChainTemplateLibrary()
    return _instance


__all__ = [
    "ChainTemplate",
    "TemplateStep",
    "TemplateVariable",
    "TemplateCategory",
    "ChainTemplateLibrary",
    "get_template_library",
]
