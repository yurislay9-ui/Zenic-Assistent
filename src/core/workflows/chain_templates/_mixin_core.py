"""
chain_templates._mixin_core — Core CRUD and search methods mixin.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from typing import Any, TYPE_CHECKING

from src.core.workflows.chain_templates._types import (
    ChainTemplate,
    TemplateStep,
    TemplateVariable,
    TemplateCategory,
)
from src.core.workflows.chain_templates._helpers import substitute_value
from src.core.workflows.chain_templates._builtins import builtin_definitions

if TYPE_CHECKING:
    from src.core.workflows.chain_composer import ComposedChain

logger = logging.getLogger(__name__)

_DB_DIR = "/".join([
    __import__("os").path.expanduser("~"),
    ".zenic_agents", "db",
])
_DB_PATH = "/".join([_DB_DIR, "chain_templates.sqlite"])


class CoreMixin:
    """Mixin providing core CRUD, search, and instantiation methods."""

    # Provided by main class
    _lock: object
    _templates: dict[str, ChainTemplate]

    # ------------------------------------------------------------------
    #  Database
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create the templates table if it does not exist."""
        __import__("os").makedirs(_DB_DIR, exist_ok=True)
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(  # nosemgrep
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
            rows = conn.execute(  # nosemgrep
                "SELECT template_id, name, description, category, "
                "event_patterns, intent_keywords, steps, variables, "
                "version, created_at FROM chain_templates"
            ).fetchall()

        for row in rows:
            template_id = row[0]
            try:
                template = ChainTemplate(
                    template_id=template_id, name=row[1], description=row[2],
                    category=row[3],
                    event_patterns=json.loads(row[4]) if row[4] else [],
                    intent_keywords=json.loads(row[5]) if row[5] else [],
                    steps=self._deserialize_steps(json.loads(row[6]) if row[6] else []),
                    variables=self._deserialize_variables(json.loads(row[7]) if row[7] else []),
                    version=row[8], created_at=row[9],
                )
                self._templates[template_id] = template
            except (json.JSONDecodeError, TypeError, KeyError) as exc:
                logger.warning("Failed to load template %s: %s", template_id, exc)

    @staticmethod
    def _serialize_steps(steps: list[TemplateStep]) -> str:
        return json.dumps([
            {"step_type": s.step_type, "config_template": s.config_template,
             "next_step_id": s.next_step_id, "condition_expr": s.condition_expr,
             "timeout_ms": s.timeout_ms}
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
            ) for s in raw
        ]

    @staticmethod
    def _serialize_variables(variables: list[TemplateVariable]) -> str:
        return json.dumps([
            {"name": v.name, "var_type": v.var_type,
             "default_value": v.default_value, "required": v.required,
             "description": v.description}
            for v in variables
        ])

    @staticmethod
    def _deserialize_variables(raw: list[dict[str, Any]]) -> list[TemplateVariable]:
        return [
            TemplateVariable(
                name=v.get("name", ""), var_type=v.get("var_type", "str"),
                default_value=v.get("default_value"),
                required=v.get("required", True),
                description=v.get("description", ""),
            ) for v in raw
        ]

    def _save_template(self, template: ChainTemplate, is_builtin: bool = False) -> None:
        """Persist a single template to SQLite."""
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(  # nosemgrep
                "INSERT OR REPLACE INTO chain_templates "
                "(template_id, name, description, category, "
                "event_patterns, intent_keywords, steps, variables, "
                "version, created_at, is_builtin) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    template.template_id, template.name, template.description,
                    template.category, json.dumps(template.event_patterns),
                    json.dumps(template.intent_keywords),
                    self._serialize_steps(template.steps),
                    self._serialize_variables(template.variables),
                    template.version, template.created_at,
                    1 if is_builtin else 0,
                ),
            )
            conn.commit()

    # ------------------------------------------------------------------
    #  CRUD
    # ------------------------------------------------------------------

    def register_template(self, template: ChainTemplate) -> str:
        """Register a new template. Returns the template_id."""
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
        """Remove a template by ID."""
        with self._lock:
            if template_id not in self._templates:
                return False
            del self._templates[template_id]
            with sqlite3.connect(_DB_PATH) as conn:
                conn.execute("DELETE FROM chain_templates WHERE template_id=?", (template_id,))  # nosemgrep
                conn.commit()
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
        """Find templates whose event_patterns match the given event_type."""
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
        """Find templates by keyword matching against intent_keywords."""
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
        """Create a concrete ComposedChain from a template with variable substitution."""
        from src.core.workflows.chain_composer import (
            ChainStep, ChainStepType, ChainStatus, ComposedChain,
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

        chain_steps: list[ChainStep] = []
        for idx, tpl_step in enumerate(template.steps):
            substituted_config = substitute_value(tpl_step.config_template, resolved_vars)
            try:
                step_type = ChainStepType(tpl_step.step_type)
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

        for i in range(len(chain_steps) - 1):
            if not chain_steps[i].next_step_id:
                chain_steps[i].next_step_id = chain_steps[i + 1].step_id

        chain_id = f"chain_{uuid.uuid4().hex[:12]}"
        composed = ComposedChain(
            chain_id=chain_id, name=template.name,
            description=template.description, steps=chain_steps,
            metadata={
                "source_template": template_id,
                "template_version": template.version,
                "category": template.category,
                "resolved_variables": list(resolved_vars.keys()),
            },
            tenant_id="", created_at=time.time(),
            status=ChainStatus.READY,
        )

        logger.info("Instantiated chain %s from template %s with %d steps",
                     chain_id, template_id, len(chain_steps))
        return composed

    # ------------------------------------------------------------------
    #  Built-in templates
    # ------------------------------------------------------------------

    def _register_builtins(self) -> None:
        """Register the five built-in templates if not already present."""
        builtins = builtin_definitions()
        for btpl in builtins:
            if btpl.template_id not in self._templates:
                self._templates[btpl.template_id] = btpl
                self._save_template(btpl, is_builtin=True)
