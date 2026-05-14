"""
ZENIC-AGENTS — EventSchemaRegistry (B1: Event-driven Actions Engine)

In-memory registry for validating event payloads against declared schemas.
Schemas specify required_fields, field_types, and field_constraints.

Usage:
    registry = EventSchemaRegistry()
    registry.register_schema("db.stock_below", {
        "required_fields": ["entity_id", "timestamp", "value"],
        "field_types": {"entity_id": "str", "timestamp": "float", "value": "float"},
        "field_constraints": {"value": {"min": 0, "max": 1000000}},
    })
    result = registry.validate("db.stock_below", {"entity_id": "AAPL", "timestamp": 1.0, "value": 150.0})
    assert result.valid
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("zenic_agents.events.schema_registry")

# ─── Type mapping ───────────────────────────────────────────────

_TYPE_MAP: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


# ─── Dataclasses ────────────────────────────────────────────────

class IssueType(str, Enum):
    """Types of validation issues."""
    MISSING = "missing"
    WRONG_TYPE = "wrong_type"
    CONSTRAINT_VIOLATION = "constraint_violation"


@dataclass
class ValidationIssue:
    """A single validation problem found in event data."""
    field: str
    issue_type: IssueType
    message: str


@dataclass
class ValidationResult:
    """Result of validating event data against a schema."""
    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    event_type: str = ""


@dataclass
class EventSchema:
    """A registered event validation schema."""
    schema_id: str
    event_type: str
    schema: dict[str, Any]  # {required_fields, field_types, field_constraints}
    created_at: float = field(default_factory=time.time)


# ─── Registry ───────────────────────────────────────────────────

class EventSchemaRegistry:
    """
    In-memory registry for event payload validation schemas.

    Thread-safe. Uses RLock for concurrent read/write access.
    Singleton pattern via get_schema_registry() / reset_schema_registry().
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._schemas_by_id: dict[str, EventSchema] = {}
        self._schemas_by_event_type: dict[str, EventSchema] = {}

    # ── Registration ────────────────────────────────────────────

    def register_schema(
        self,
        event_type: str,
        schema: dict[str, Any],
    ) -> str:
        """
        Register a validation schema for an event type.

        Args:
            event_type: Dot-notation event type (e.g. "db.stock_below").
            schema: Dict with optional keys:
                - required_fields: list[str]
                - field_types: dict[str, str]
                - field_constraints: dict[str, dict[str, Any]]

        Returns:
            schema_id (unique string).
        """
        if not event_type or not isinstance(event_type, str):
            raise ValueError("event_type must be a non-empty string")
        if not isinstance(schema, dict):
            raise ValueError("schema must be a dict")

        schema_id = f"sch_{uuid.uuid4().hex[:12]}"
        entry = EventSchema(
            schema_id=schema_id,
            event_type=event_type,
            schema={
                "required_fields": schema.get("required_fields", []),
                "field_types": schema.get("field_types", {}),
                "field_constraints": schema.get("field_constraints", {}),
            },
        )

        with self._lock:
            # Remove previous schema for same event_type if any
            old = self._schemas_by_event_type.pop(event_type, None)
            if old is not None:
                self._schemas_by_id.pop(old.schema_id, None)

            self._schemas_by_id[schema_id] = entry
            self._schemas_by_event_type[event_type] = entry

        logger.info(
            "SchemaRegistry: registered schema %s for event_type=%s",
            schema_id, event_type,
        )
        return schema_id

    def unregister_schema(self, schema_id: str) -> bool:
        """
        Unregister a schema by its ID.

        Returns:
            True if found and removed, False otherwise.
        """
        with self._lock:
            entry = self._schemas_by_id.pop(schema_id, None)
            if entry is None:
                return False
            # Also remove from event_type index
            if self._schemas_by_event_type.get(entry.event_type) is entry:
                self._schemas_by_event_type.pop(entry.event_type, None)
            logger.info(
                "SchemaRegistry: unregistered schema %s", schema_id,
            )
            return True

    # ── Validation ──────────────────────────────────────────────

    def validate(
        self,
        event_type: str,
        data: dict[str, Any],
    ) -> ValidationResult:
        """
        Validate event data against the registered schema for event_type.

        If no schema is registered, returns valid=True (permissive by default).
        """
        if not isinstance(data, dict):
            return ValidationResult(
                valid=False,
                issues=[ValidationIssue(
                    field="",
                    issue_type=IssueType.WRONG_TYPE,
                    message=f"Expected dict, got {type(data).__name__}",
                )],
                event_type=event_type,
            )

        with self._lock:
            schema_entry = self._schemas_by_event_type.get(event_type)

        if schema_entry is None:
            # No schema registered → permissive pass
            return ValidationResult(valid=True, issues=[], event_type=event_type)

        schema = schema_entry.schema
        issues: list[ValidationIssue] = []

        # 1. Check required fields
        required_fields: list[str] = schema.get("required_fields", [])
        for fld in required_fields:
            if fld not in data:
                issues.append(ValidationIssue(
                    field=fld,
                    issue_type=IssueType.MISSING,
                    message=f"Required field '{fld}' is missing",
                ))

        # 2. Check field types
        field_types: dict[str, str] = schema.get("field_types", {})
        for fld, type_name in field_types.items():
            if fld not in data:
                continue  # Already reported as missing
            expected_type = _TYPE_MAP.get(type_name)
            if expected_type is None:
                logger.warning(
                    "SchemaRegistry: unknown type '%s' for field '%s', skipping type check",
                    type_name, fld,
                )
                continue
            value = data[fld]
            # Allow int where float is expected (numeric coercion)
            if expected_type is float and isinstance(value, int) and not isinstance(value, bool):
                continue
            if not isinstance(value, expected_type):
                issues.append(ValidationIssue(
                    field=fld,
                    issue_type=IssueType.WRONG_TYPE,
                    message=(
                        f"Field '{fld}' expected type {expected_type.__name__}, "
                        f"got {type(value).__name__}"
                    ),
                ))

        # 3. Check field constraints
        field_constraints: dict[str, dict[str, Any]] = schema.get("field_constraints", {})
        for fld, constraints in field_constraints.items():
            if fld not in data:
                continue
            value = data[fld]
            for constraint_name, constraint_val in constraints.items():
                issue_msg = self._check_constraint(fld, value, constraint_name, constraint_val)
                if issue_msg is not None:
                    issues.append(ValidationIssue(
                        field=fld,
                        issue_type=IssueType.CONSTRAINT_VIOLATION,
                        message=issue_msg,
                    ))

        valid = len(issues) == 0
        return ValidationResult(
            valid=valid,
            issues=issues,
            event_type=event_type,
        )

    # ── Query ───────────────────────────────────────────────────

    def get_schema(self, event_type: str) -> dict[str, Any] | None:
        """Return the schema dict for an event_type, or None."""
        with self._lock:
            entry = self._schemas_by_event_type.get(event_type)
        if entry is None:
            return None
        return entry.schema

    def list_schemas(self) -> list[dict[str, Any]]:
        """Return a list of all registered schemas as dicts."""
        with self._lock:
            result = []
            for entry in self._schemas_by_id.values():
                result.append({
                    "schema_id": entry.schema_id,
                    "event_type": entry.event_type,
                    "schema": entry.schema,
                    "created_at": entry.created_at,
                })
            return result

    # ── Internals ───────────────────────────────────────────────

    @staticmethod
    def _check_constraint(
        field_name: str,
        value: Any,
        constraint_name: str,
        constraint_val: Any,
    ) -> str | None:
        """
        Check a single constraint. Returns an error message string if violated,
        or None if the constraint passes.
        """
        try:
            if constraint_name == "min":
                if not isinstance(value, (int, float)):
                    return f"Constraint 'min' on '{field_name}' requires numeric value"
                if value < constraint_val:
                    return (
                        f"Field '{field_name}' value {value} is below "
                        f"minimum {constraint_val}"
                    )
            elif constraint_name == "max":
                if not isinstance(value, (int, float)):
                    return f"Constraint 'max' on '{field_name}' requires numeric value"
                if value > constraint_val:
                    return (
                        f"Field '{field_name}' value {value} exceeds "
                        f"maximum {constraint_val}"
                    )
            elif constraint_name == "min_length":
                if not isinstance(value, (str, list)):
                    return f"Constraint 'min_length' on '{field_name}' requires str or list"
                if len(value) < constraint_val:
                    return (
                        f"Field '{field_name}' length {len(value)} is below "
                        f"minimum {constraint_val}"
                    )
            elif constraint_name == "max_length":
                if not isinstance(value, (str, list)):
                    return f"Constraint 'max_length' on '{field_name}' requires str or list"
                if len(value) > constraint_val:
                    return (
                        f"Field '{field_name}' length {len(value)} exceeds "
                        f"maximum {constraint_val}"
                    )
            elif constraint_name == "pattern":
                import re
                if not isinstance(value, str):
                    return f"Constraint 'pattern' on '{field_name}' requires str"
                if not re.search(constraint_val, value):
                    return (
                        f"Field '{field_name}' value does not match "
                        f"pattern '{constraint_val}'"
                    )
            elif constraint_name == "allowed":
                if value not in constraint_val:
                    return (
                        f"Field '{field_name}' value {value!r} not in "
                        f"allowed values {constraint_val}"
                    )
            else:
                logger.warning(
                    "SchemaRegistry: unknown constraint '%s' on field '%s'",
                    constraint_name, field_name,
                )
        except Exception as exc:
            logger.error(
                "SchemaRegistry: error checking constraint '%s' on '%s': %s",
                constraint_name, field_name, exc,
            )
            return f"Error checking constraint '{constraint_name}' on '{field_name}': {exc}"

        return None


# ─── Singleton ──────────────────────────────────────────────────

_instance: EventSchemaRegistry | None = None
_instance_lock = threading.Lock()


def get_schema_registry() -> EventSchemaRegistry:
    """Return the singleton EventSchemaRegistry instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = EventSchemaRegistry()
    return _instance


def reset_schema_registry() -> None:
    """Reset the singleton (mainly for testing)."""
    global _instance
    with _instance_lock:
        _instance = None


__all__ = [
    "EventSchemaRegistry",
    "EventSchema",
    "ValidationResult",
    "ValidationIssue",
    "IssueType",
    "get_schema_registry",
    "reset_schema_registry",
]
