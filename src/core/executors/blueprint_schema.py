"""
ZENIC-AGENTS - Blueprint Schema for Executors (Phase 3)

Blueprint parameterization system that provides structured schemas
for executor configuration. Each Blueprint defines:
  - metadata (name, version, domain)
  - executor config schemas (validation rules for each executor type)
  - business rules (domain-specific constraints)
  - monitors (SNA integration hooks)
  - actions (predefined action templates)

Blueprints are signed with ECDSA for certification.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Optional YAML support
try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


# ──────────────────────────────────────────────────────────────
#  TYPES
# ──────────────────────────────────────────────────────────────

@dataclass
class ExecutorSchema:
    """Schema definition for a specific executor type within a Blueprint."""
    executor_type: str                          # e.g., "email", "database", "notification"
    required_fields: List[str] = field(default_factory=list)
    optional_fields: List[str] = field(default_factory=list)
    field_types: Dict[str, str] = field(default_factory=dict)   # field_name → type
    field_defaults: Dict[str, Any] = field(default_factory=dict)
    field_validators: Dict[str, str] = field(default_factory=dict)  # field_name → regex pattern
    max_records: int = 0                        # 0 = unlimited
    allowed_operations: List[str] = field(default_factory=list)
    denied_operations: List[str] = field(default_factory=list)
    rate_limits: Dict[str, int] = field(default_factory=dict)   # operation → max/hour


@dataclass
class BusinessRule:
    """A domain-specific business rule enforced by the Blueprint."""
    name: str
    description: str
    executor_type: str                          # Which executor this applies to
    condition: str                              # Condition expression
    action: str                                 # What to do when condition met
    severity: str = "warning"                   # warning, error, block


@dataclass
class ActionTemplate:
    """A predefined action template within a Blueprint."""
    name: str
    description: str
    executor_type: str
    config_template: Dict[str, Any] = field(default_factory=dict)
    safety_category: str = "moderate"           # safe, moderate, destructive, financial
    requires_confirmation: bool = False
    requires_approval: bool = False


@dataclass
class BlueprintMetadata:
    """Metadata about a Blueprint."""
    name: str
    version: str = "1.0.0"
    domain: str = ""                            # e.g., "retail", "manufacturing"
    description: str = ""
    author: str = ""
    signature: str = ""                         # ECDSA signature (future)
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class Blueprint:
    """A certified Blueprint that parameterizes executor behavior.

    Defines schemas, rules, and templates for a specific domain.
    Executors consult their Blueprint before executing actions.
    """
    metadata: BlueprintMetadata
    executor_schemas: Dict[str, ExecutorSchema] = field(default_factory=dict)
    business_rules: List[BusinessRule] = field(default_factory=list)
    action_templates: Dict[str, ActionTemplate] = field(default_factory=dict)
    monitor_hooks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    compatible_with: List[str] = field(default_factory=list)  # Other Blueprint names


# ──────────────────────────────────────────────────────────────
#  BLUEPRINT VALIDATOR
# ──────────────────────────────────────────────────────────────

class BlueprintValidator:
    """Validates executor config against a Blueprint's schema."""

    @staticmethod
    def validate_config(
        config: Dict[str, Any],
        schema: ExecutorSchema,
    ) -> List[str]:
        """Validate an executor config against a schema.

        Returns a list of validation errors (empty = valid).
        """
        errors: List[str] = []

        # Check required fields
        for req_field in schema.required_fields:
            if req_field not in config or config[req_field] is None:
                errors.append(f"Missing required field: {req_field}")

        # Check field types
        for field_name, expected_type in schema.field_types.items():
            if field_name not in config:
                continue
            value = config[field_name]
            type_valid = BlueprintValidator._check_type(value, expected_type)
            if not type_valid:
                errors.append(
                    f"Field '{field_name}' has wrong type: "
                    f"expected {expected_type}, got {type(value).__name__}"
                )

        # Check field validators (regex patterns)
        for field_name, pattern in schema.field_validators.items():
            if field_name not in config:
                continue
            value = str(config[field_name])
            if not re.match(pattern, value):
                errors.append(
                    f"Field '{field_name}' failed validation pattern: {pattern}"
                )

        # Check denied operations
        operation = str(config.get("operation", "")).lower()
        if operation and schema.denied_operations:
            if operation in schema.denied_operations:
                errors.append(
                    f"Operation '{operation}' is denied by Blueprint schema"
                )

        # Check max records
        if schema.max_records > 0:
            params = config.get("params", [])
            if isinstance(params, (list, tuple)) and len(params) > schema.max_records:
                errors.append(
                    f"Too many records: {len(params)} > max {schema.max_records}"
                )

        return errors

    @staticmethod
    def _check_type(value: Any, expected: str) -> bool:
        """Check if a value matches an expected type string."""
        type_map = {
            "str": str, "string": str,
            "int": int, "integer": int,
            "float": float, "number": (int, float),
            "bool": bool, "boolean": bool,
            "list": list, "array": list,
            "dict": dict, "object": dict,
        }
        expected_type = type_map.get(expected.lower())
        if expected_type is None:
            return True  # Unknown type, skip
        return isinstance(value, expected_type)


# ──────────────────────────────────────────────────────────────
#  BLUEPRINT LOADER
# ──────────────────────────────────────────────────────────────

class BlueprintLoader:
    """Loads and composes Blueprints from YAML/JSON files or dicts."""

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> Blueprint:
        """Create a Blueprint from a dictionary."""
        meta_data = data.get("metadata", {})
        metadata = BlueprintMetadata(
            name=meta_data.get("name", "unnamed"),
            version=meta_data.get("version", "1.0.0"),
            domain=meta_data.get("domain", ""),
            description=meta_data.get("description", ""),
            author=meta_data.get("author", ""),
        )

        # Parse executor schemas
        executor_schemas: Dict[str, ExecutorSchema] = {}
        for exec_type, schema_data in data.get("executors", {}).items():
            executor_schemas[exec_type] = ExecutorSchema(
                executor_type=exec_type,
                required_fields=schema_data.get("required", []),
                optional_fields=schema_data.get("optional", []),
                field_types=schema_data.get("types", {}),
                field_defaults=schema_data.get("defaults", {}),
                field_validators=schema_data.get("validators", {}),
                max_records=schema_data.get("max_records", 0),
                allowed_operations=schema_data.get("allowed_operations", []),
                denied_operations=schema_data.get("denied_operations", []),
                rate_limits=schema_data.get("rate_limits", {}),
            )

        # Parse business rules
        business_rules: List[BusinessRule] = []
        for rule_data in data.get("rules", []):
            business_rules.append(BusinessRule(
                name=rule_data.get("name", ""),
                description=rule_data.get("description", ""),
                executor_type=rule_data.get("executor_type", ""),
                condition=rule_data.get("condition", ""),
                action=rule_data.get("action", ""),
                severity=rule_data.get("severity", "warning"),
            ))

        # Parse action templates
        action_templates: Dict[str, ActionTemplate] = {}
        for tmpl_name, tmpl_data in data.get("actions", {}).items():
            action_templates[tmpl_name] = ActionTemplate(
                name=tmpl_name,
                description=tmpl_data.get("description", ""),
                executor_type=tmpl_data.get("executor_type", ""),
                config_template=tmpl_data.get("config", {}),
                safety_category=tmpl_data.get("safety_category", "moderate"),
                requires_confirmation=tmpl_data.get("requires_confirmation", False),
                requires_approval=tmpl_data.get("requires_approval", False),
            )

        return Blueprint(
            metadata=metadata,
            executor_schemas=executor_schemas,
            business_rules=business_rules,
            action_templates=action_templates,
            monitor_hooks=data.get("monitors", {}),
            compatible_with=data.get("compatible_with", []),
        )

    @staticmethod
    def from_yaml(yaml_str: str) -> Blueprint:
        """Create a Blueprint from a YAML string."""
        if not _HAS_YAML:
            raise ImportError("PyYAML is required for YAML Blueprint loading")
        data = _yaml.safe_load(yaml_str)
        return BlueprintLoader.from_dict(data)

    @staticmethod
    def from_file(filepath: str) -> Blueprint:
        """Load a Blueprint from a YAML or JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        if filepath.endswith((".yaml", ".yml")):
            return BlueprintLoader.from_yaml(content)
        return BlueprintLoader.from_dict(json.loads(content))

    @staticmethod
    def compose(blueprints: List[Blueprint]) -> Blueprint:
        """Compose multiple Blueprints into one.

        Merges schemas, rules, and templates.
        Later blueprints override earlier ones for conflicts.
        """
        if not blueprints:
            return Blueprint(metadata=BlueprintMetadata(name="empty"))

        # Start with first blueprint
        result = Blueprint(
            metadata=BlueprintMetadata(
                name="+".join(bp.metadata.name for bp in blueprints),
                domain="composed",
            ),
        )

        for bp in blueprints:
            # Merge executor schemas (later wins on conflict)
            result.executor_schemas.update(bp.executor_schemas)

            # Append business rules
            result.business_rules.extend(bp.business_rules)

            # Merge action templates (later wins on conflict)
            result.action_templates.update(bp.action_templates)

            # Merge monitor hooks
            result.monitor_hooks.update(bp.monitor_hooks)

        # Track compatibility (outside loop to avoid duplicates)
        result.compatible_with.extend(bp.metadata.name for bp in blueprints)

        return result


# ──────────────────────────────────────────────────────────────
#  BUILT-IN BLUEPRINTS
# ──────────────────────────────────────────────────────────────

def get_default_blueprint() -> Blueprint:
    """Get the default (minimal safety) Blueprint."""
    return BlueprintLoader.from_dict({
        "metadata": {"name": "default", "domain": "general", "version": "1.0.0"},
        "executors": {
            "database": {
                "required": ["operation"],
                "denied_operations": ["drop", "truncate"],
                "rate_limits": {"delete": 20, "update": 50, "insert": 100},
            },
            "email": {
                "required": ["to", "subject", "body"],
                "validators": {"to": r"^[^@]+@[^@]+\.[^@]+$"},
                "rate_limits": {"send": 30},
            },
            "notification": {
                "rate_limits": {"send": 60},
            },
            "file": {
                "denied_operations": [],
                "rate_limits": {"delete": 10, "write": 100},
            },
            "http": {
                "rate_limits": {"POST": 50, "DELETE": 10},
            },
            "webhook": {
                "required": ["url"],
                "rate_limits": {"send": 30},
            },
            "discord": {
                "rate_limits": {"send": 30},
            },
            "schedule": {
                "rate_limits": {"add": 10},
            },
            "transform": {},
        },
        "rules": [
            {
                "name": "no_bulk_delete_without_confirm",
                "description": "Bulk DELETE operations require confirmation",
                "executor_type": "database",
                "condition": "operation == 'delete' and record_count > 1",
                "action": "require_confirmation",
                "severity": "block",
            },
            {
                "name": "financial_email_requires_approval",
                "description": "Financial emails require approval",
                "executor_type": "email",
                "condition": "subject contains 'invoice' or 'payment'",
                "action": "require_approval",
                "severity": "block",
            },
        ],
        "actions": {
            "send_invoice": {
                "description": "Send an invoice email",
                "executor_type": "email",
                "config": {
                    "subject": "Invoice #{invoice_number}",
                    "html": "<h1>Invoice</h1><p>Amount: {amount}</p>",
                },
                "safety_category": "financial",
                "requires_approval": True,
            },
        },
    })
