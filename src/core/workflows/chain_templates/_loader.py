"""
ZENIC-AGENTS — Chain template persistence layer.

SQLite-based storage functions for loading, saving, and serializing
chain templates. Extracted from ChainTemplateLibrary for modularity.
"""

from __future__ import annotations

import json
import sqlite3

from typing import Any

from ._types import (
    ChainTemplate,
    TemplateStep,
    TemplateVariable,
    _DB_DIR,
    _DB_PATH,
    logger,
)

import os  # noqa: E402 – needed for makedirs


# ---------------------------------------------------------------------------
#  Database initialization
# ---------------------------------------------------------------------------


def init_db() -> None:
    """Create the templates table if it does not exist."""
    os.makedirs(_DB_DIR, exist_ok=True)
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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


# ---------------------------------------------------------------------------
#  Serialization helpers
# ---------------------------------------------------------------------------


def serialize_steps(steps: list[TemplateStep]) -> str:
    """Serialize a list of TemplateStep to a JSON string."""
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


def deserialize_steps(raw: list[dict[str, Any]]) -> list[TemplateStep]:
    """Deserialize a list of dicts into TemplateStep instances."""
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


def serialize_variables(variables: list[TemplateVariable]) -> str:
    """Serialize a list of TemplateVariable to a JSON string."""
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


def deserialize_variables(raw: list[dict[str, Any]]) -> list[TemplateVariable]:
    """Deserialize a list of dicts into TemplateVariable instances."""
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


# ---------------------------------------------------------------------------
#  Load / Save
# ---------------------------------------------------------------------------


def load_templates_from_db() -> dict[str, ChainTemplate]:
    """Load all persisted templates from SQLite.

    Returns a dict mapping template_id → ChainTemplate.
    """
    templates: dict[str, ChainTemplate] = {}
    with sqlite3.connect(_DB_PATH) as conn:
        rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
                steps=deserialize_steps(json.loads(row[6]) if row[6] else []),
                variables=deserialize_variables(json.loads(row[7]) if row[7] else []),
                version=row[8],
                created_at=row[9],
            )
            templates[template_id] = template
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.warning("Failed to load template %s: %s", template_id, exc)

    return templates


def save_template_to_db(template: ChainTemplate, is_builtin: bool = False) -> None:
    """Persist a single template to SQLite."""
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
                serialize_steps(template.steps),
                serialize_variables(template.variables),
                template.version,
                template.created_at,
                1 if is_builtin else 0,
            ),
        )
        conn.commit()


def delete_template_from_db(template_id: str) -> None:
    """Delete a template row from SQLite by its ID."""
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
            "DELETE FROM chain_templates WHERE template_id=?", (template_id,)
        )
        conn.commit()
