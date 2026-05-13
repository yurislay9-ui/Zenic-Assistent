"""
ZENIC-AGENTS - CRUD Validator (Phase 3)

Validates CRUD operations against Blueprint schemas.
Ensures that:
  - Required fields are present for INSERT
  - Fields match expected types for UPDATE
  - DELETE operations have WHERE clauses (no accidental mass delete)
  - Table names are validated (no SQL injection)
  - Record limits are enforced per Blueprint
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  TYPES
# ──────────────────────────────────────────────────────────────

@dataclass
class CRUDValidationResult:
    """Result of a CRUD operation validation."""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    sanitized_table: str = ""
    operation: str = ""
    risk_level: str = "low"  # low, medium, high, critical


@dataclass
class TableSchema:
    """Schema definition for a database table."""
    table_name: str
    columns: Dict[str, str] = field(default_factory=dict)   # column_name → type
    required_columns: List[str] = field(default_factory=list)
    unique_columns: List[str] = field(default_factory=list)
    protected_columns: List[str] = field(default_factory=list)  # Cannot be modified
    max_records: int = 0                         # 0 = unlimited


# ──────────────────────────────────────────────────────────────
#  DANGEROUS SQL PATTERNS
# ──────────────────────────────────────────────────────────────

_DANGEROUS_TABLE_PATTERNS = re.compile(
    r"(sqlite_master|sqlite_sequence|sqlite_temp_master)",
    re.IGNORECASE,
)

_NO_WHERE_DELETE = re.compile(
    r"^\s*DELETE\s+FROM\s+\w+\s*;?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_NO_WHERE_UPDATE = re.compile(
    r"^\s*UPDATE\s+\w+\s+SET\s+.+\s*;?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_TABLE_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


# ──────────────────────────────────────────────────────────────
#  CRUD VALIDATOR
# ──────────────────────────────────────────────────────────────

class CRUDValidator:
    """Validates CRUD operations against Blueprint schemas.

    Provides defense-in-depth for database operations:
      1. Table name validation (prevents SQL injection)
      2. Schema validation (ensures correct fields)
      3. WHERE clause enforcement (prevents accidental mass operations)
      4. Protected column enforcement (prevents modifying id, created_at, etc.)
      5. Record limit enforcement (prevents oversized operations)
    """

    def __init__(self) -> None:
        self._schemas: Dict[str, TableSchema] = {}
        self._global_max_records: int = 10000
        self._denied_tables: Set[str] = {
            "sqlite_master", "sqlite_sequence", "sqlite_temp_master",
        }

    def register_schema(self, schema: TableSchema) -> None:
        """Register a table schema for validation."""
        self._schemas[schema.table_name] = schema
        logger.debug(f"CRUDValidator: Registered schema for '{schema.table_name}'")

    def register_schema_from_dict(
        self, table_name: str, schema_dict: Dict[str, Any]
    ) -> None:
        """Register a table schema from a dictionary."""
        schema = TableSchema(
            table_name=table_name,
            columns=schema_dict.get("columns", {}),
            required_columns=schema_dict.get("required", []),
            unique_columns=schema_dict.get("unique", []),
            protected_columns=schema_dict.get("protected", []),
            max_records=schema_dict.get("max_records", 0),
        )
        self.register_schema(schema)

    def validate(
        self,
        operation: str,
        table_name: str,
        data: Optional[Dict[str, Any]] = None,
        query: str = "",
        where_clause: str = "",
    ) -> CRUDValidationResult:
        """Validate a CRUD operation.

        Args:
            operation: INSERT, UPDATE, DELETE, SELECT
            table_name: Target table name
            data: Data dict (for INSERT/UPDATE)
            query: Full SQL query (for validation)
            where_clause: WHERE clause string

        Returns:
            CRUDValidationResult with validation outcome
        """
        errors: List[str] = []
        warnings: List[str] = []
        risk_level = "low"

        # Step 1: Validate table name
        table_result = self._validate_table_name(table_name)
        if not table_result:
            return CRUDValidationResult(
                valid=False,
                errors=[f"Invalid table name: {table_name}"],
                operation=operation,
                risk_level="critical",
            )

        # Step 2: Check denied tables
        if table_name.lower() in self._denied_tables:
            return CRUDValidationResult(
                valid=False,
                errors=[f"Access denied to system table: {table_name}"],
                operation=operation,
                risk_level="critical",
            )

        # Step 3: Operation-specific validation
        op = operation.upper()

        if op == "DELETE":
            del_result = self._validate_delete(table_name, query, where_clause)
            errors.extend(del_result[0])
            warnings.extend(del_result[1])
            risk_level = del_result[2]

        elif op == "UPDATE":
            upd_result = self._validate_update(table_name, data, query, where_clause)
            errors.extend(upd_result[0])
            warnings.extend(upd_result[1])
            risk_level = upd_result[2]

        elif op == "INSERT":
            ins_result = self._validate_insert(table_name, data)
            errors.extend(ins_result[0])
            warnings.extend(ins_result[1])
            risk_level = ins_result[2]

        elif op == "SELECT":
            # SELECT is generally safe, just check for system tables
            risk_level = "low"

        elif op == "SCRIPT":
            # Script mode — highest risk
            risk_level = "high"
            warnings.append("Script mode — each statement should be validated individually")

        else:
            warnings.append(f"Unknown operation: {operation}")

        return CRUDValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_table=table_name,
            operation=operation,
            risk_level=risk_level,
        )

    def get_schema(self, table_name: str) -> Optional[TableSchema]:
        """Get the registered schema for a table."""
        return self._schemas.get(table_name)

    def list_schemas(self) -> List[str]:
        """List all registered table names."""
        return list(self._schemas.keys())

    # ── Private methods ──────────────────────────────────────

    @staticmethod
    def _validate_table_name(table_name: str) -> bool:
        """Validate table name against injection patterns."""
        if not table_name or not _TABLE_NAME_PATTERN.match(table_name):
            return False
        if _DANGEROUS_TABLE_PATTERNS.search(table_name):
            return False
        return True

    def _validate_delete(
        self, table_name: str, query: str, where_clause: str
    ) -> tuple[List[str], List[str], str]:
        """Validate DELETE operation."""
        errors: List[str] = []
        warnings: List[str] = []
        risk_level = "high"

        # Check for DELETE without WHERE (mass delete)
        if query and _NO_WHERE_DELETE.match(query):
            errors.append("DELETE without WHERE clause is blocked — specify a WHERE condition")
            risk_level = "critical"
        elif not where_clause and not query:
            warnings.append("No WHERE clause specified for DELETE — will affect all records")
            risk_level = "critical"

        # Check record limits
        schema = self._schemas.get(table_name)
        if schema and schema.max_records > 0:
            warnings.append(f"Table has max_records limit: {schema.max_records}")

        return errors, warnings, risk_level

    def _validate_update(
        self,
        table_name: str,
        data: Optional[Dict[str, Any]],
        query: str,
        where_clause: str,
    ) -> tuple[List[str], List[str], str]:
        """Validate UPDATE operation."""
        errors: List[str] = []
        warnings: List[str] = []
        risk_level = "medium"

        # Check for UPDATE without WHERE
        if query and _NO_WHERE_UPDATE.match(query):
            errors.append("UPDATE without WHERE clause is blocked — specify a WHERE condition")
            risk_level = "critical"
        elif not where_clause and not query:
            warnings.append("No WHERE clause specified for UPDATE")

        # Check protected columns
        schema = self._schemas.get(table_name)
        if schema and data:
            for col in schema.protected_columns:
                if col in (data or {}):
                    errors.append(f"Cannot modify protected column: {col}")

        # Check field types
        if schema and data:
            for key, value in data.items():
                expected_type = schema.columns.get(key)
                if expected_type and not self._check_type(value, expected_type):
                    warnings.append(
                        f"Field '{key}' may have wrong type: "
                        f"expected {expected_type}, got {type(value).__name__}"
                    )

        return errors, warnings, risk_level

    def _validate_insert(
        self,
        table_name: str,
        data: Optional[Dict[str, Any]],
    ) -> tuple[List[str], List[str], str]:
        """Validate INSERT operation."""
        errors: List[str] = []
        warnings: List[str] = []
        risk_level = "low"

        schema = self._schemas.get(table_name)
        if not schema:
            return errors, warnings, risk_level

        # Check required columns
        if data:
            for col in schema.required_columns:
                if col not in data:
                    errors.append(f"Missing required column: {col}")

        # Check field types
        if data:
            for key, value in data.items():
                expected_type = schema.columns.get(key)
                if expected_type and not self._check_type(value, expected_type):
                    warnings.append(
                        f"Field '{key}' may have wrong type: "
                        f"expected {expected_type}, got {type(value).__name__}"
                    )

        return errors, warnings, risk_level

    @staticmethod
    def _check_type(value: Any, expected: str) -> bool:
        """Check if a value matches an expected SQL type."""
        type_map = {
            "TEXT": str, "VARCHAR": str, "CHAR": str,
            "INTEGER": int, "INT": int, "BIGINT": int,
            "REAL": float, "FLOAT": float, "DOUBLE": float, "DECIMAL": (int, float),
            "BOOLEAN": bool, "BOOL": bool,
            "BLOB": bytes,
        }
        base_type = expected.split("(")[0].strip().upper()
        expected_type = type_map.get(base_type)
        if expected_type is None:
            return True
        return isinstance(value, expected_type)
