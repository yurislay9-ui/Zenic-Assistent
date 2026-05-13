"""
ZENIC-AGENTS - Validation Logic Blocks

Validation and sanitization blocks: required, types, ranges, unique, sanitize.
"""

import re
import logging
from typing import Any, Dict, List
from copy import deepcopy

from .chain import LogicBlock, _validate_identifier

logger = logging.getLogger(__name__)


# ============================================================
#  VALIDATION BLOCKS (5)
# ============================================================


class ValidateRequiredBlock(LogicBlock):
    """Verifica que campos requeridos existan en los datos."""

    name = "validate_required"
    category = "validation"
    description = "Check that required fields exist in data"
    inputs = ["data", "required_fields"]
    outputs = ["valid", "errors", "missing"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            required = data.get("required_fields", data.get("_required_fields", []))
            if isinstance(required, str):
                required = [r.strip() for r in required.split(",")]

            missing = []
            errors = []
            for field_name in required:
                value = data.get(field_name)
                if value is None or (isinstance(value, str) and value.strip() == ""):
                    missing.append(field_name)
                    errors.append(f"Field '{field_name}' is required")

            is_valid = len(missing) == 0
            logger.debug(f"ValidateRequiredBlock: valid={is_valid}, missing={missing}")
            return {
                "success": True,
                "valid": is_valid,
                "errors": errors,
                "missing": missing,
            }
        except Exception as e:
            return {"success": False, "error": f"ValidateRequiredBlock: {str(e)}"}


class ValidateTypesBlock(LogicBlock):
    """Verifica que los tipos de campos coincidan con un schema."""

    name = "validate_types"
    category = "validation"
    description = "Check field types match a schema definition"
    inputs = ["data", "type_schema"]
    outputs = ["valid", "errors", "type_mismatches"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            schema = data.get("type_schema", data.get("_type_schema", {}))
            errors = []
            mismatches = []

            type_map = {
                "str": str, "string": str,
                "int": int, "integer": int,
                "float": float, "number": (int, float),
                "bool": bool, "boolean": bool,
                "list": list, "array": list,
                "dict": dict, "object": dict,
            }

            for field_name, expected_type in schema.items():
                if field_name not in data:
                    continue  # Skip missing fields (use validate_required for that)
                value = data[field_name]
                python_type = type_map.get(expected_type, None)
                if python_type and not isinstance(value, python_type):
                    # Allow int for float fields
                    if python_type == float and isinstance(value, int):
                        continue
                    mismatches.append({
                        "field": field_name,
                        "expected": expected_type,
                        "actual": type(value).__name__,
                    })
                    errors.append(
                        f"Field '{field_name}' expected {expected_type}, got {type(value).__name__}"
                    )

            is_valid = len(errors) == 0
            logger.debug(f"ValidateTypesBlock: valid={is_valid}, mismatches={len(mismatches)}")
            return {
                "success": True,
                "valid": is_valid,
                "errors": errors,
                "type_mismatches": mismatches,
            }
        except Exception as e:
            return {"success": False, "error": f"ValidateTypesBlock: {str(e)}"}


class ValidateRangesBlock(LogicBlock):
    """Verifica rangos numericos (min, max) para campos."""

    name = "validate_ranges"
    category = "validation"
    description = "Check numeric ranges (min, max) for fields"
    inputs = ["data", "range_schema"]
    outputs = ["valid", "errors", "violations"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            range_schema = data.get("range_schema", data.get("_range_schema", {}))
            errors = []
            violations = []

            for field_name, constraints in range_schema.items():
                value = data.get(field_name)
                if value is None:
                    continue
                try:
                    numeric_value = float(value)
                except (ValueError, TypeError):
                    continue

                min_val = constraints.get("min", constraints.get("minimum", None))
                max_val = constraints.get("max", constraints.get("maximum", None))

                if min_val is not None and numeric_value < float(min_val):
                    violations.append({"field": field_name, "value": numeric_value, "min": min_val})
                    errors.append(f"Field '{field_name}' value {numeric_value} below minimum {min_val}")

                if max_val is not None and numeric_value > float(max_val):
                    violations.append({"field": field_name, "value": numeric_value, "max": max_val})
                    errors.append(f"Field '{field_name}' value {numeric_value} above maximum {max_val}")

            is_valid = len(errors) == 0
            logger.debug(f"ValidateRangesBlock: valid={is_valid}, violations={len(violations)}")
            return {
                "success": True,
                "valid": is_valid,
                "errors": errors,
                "violations": violations,
            }
        except Exception as e:
            return {"success": False, "error": f"ValidateRangesBlock: {str(e)}"}


class ValidateUniqueBlock(LogicBlock):
    """Verifica unicidad contra base de datos."""

    name = "validate_unique"
    category = "validation"
    description = "Check uniqueness of field value against database"
    inputs = ["data", "field", "table"]
    outputs = ["is_unique", "existing"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            field_name = data.get("unique_field", data.get("field", "email"))
            table_name = data.get("table", data.get("_table", "users"))
            value = data.get(field_name)

            if value is None:
                return {"success": True, "is_unique": False, "error": f"Field '{field_name}' not provided"}

            # Check against database if available
            db = context.get("db", None)
            existing = None

            if db is not None:
                try:
                    # Validate identifiers to prevent SQL injection
                    _validate_identifier(field_name)
                    _validate_identifier(table_name)
                    cursor = db.execute(
                        f'SELECT id, "{field_name}" FROM "{table_name}" WHERE "{field_name}" = ?',
                        (value,)
                    )
                    row = cursor.fetchone() if hasattr(cursor, 'fetchone') else None
                    if row:
                        existing = dict(row) if hasattr(row, 'keys') else {"id": row[0], field_name: row[1]}
                except Exception as db_err:
                    logger.warning(f"ValidateUniqueBlock: DB check failed: {db_err}")
                    # Fallback: assume unique when DB unavailable
                    existing = None

            is_unique = existing is None
            logger.debug(f"ValidateUniqueBlock: field={field_name}, value={value}, unique={is_unique}")
            return {
                "success": True,
                "is_unique": is_unique,
                "existing": existing,
                "checked_field": field_name,
                "checked_value": value,
            }
        except Exception as e:
            return {"success": False, "error": f"ValidateUniqueBlock: {str(e)}"}


class SanitizeBlock(LogicBlock):
    """Sanitizacion XSS/injection para campos string."""

    name = "sanitize"
    category = "validation"
    description = "XSS and injection sanitization for string fields"
    inputs = ["data", "fields"]
    outputs = ["data", "sanitized_fields"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            fields_to_sanitize = data.get("sanitize_fields", data.get("fields", []))
            if isinstance(fields_to_sanitize, str):
                fields_to_sanitize = [f.strip() for f in fields_to_sanitize.split(",")]

            sanitized = {}
            result_data = deepcopy(data)

            # XSS patterns
            xss_patterns = [
                (r'<script[^>]*>.*?</script>', '', re.IGNORECASE | re.DOTALL),
                (r'javascript:', '', re.IGNORECASE),
                (r'on\w+\s*=', '', re.IGNORECASE),
                (r'<iframe[^>]*>.*?</iframe>', '', re.IGNORECASE | re.DOTALL),
                (r'<object[^>]*>.*?</object>', '', re.IGNORECASE | re.DOTALL),
            ]

            # SQL injection patterns
            sql_patterns = [
                (r"('|\");?\s*(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|EXEC)\s", '', re.IGNORECASE),
                (r"(--|/\*|\*/)", '', re.IGNORECASE),
                (r"(\bOR\b\s+\d+\s*=\s*\d+)", '', re.IGNORECASE),
                (r"(\bUNION\b\s+\bSELECT\b)", '', re.IGNORECASE),
            ]

            all_patterns = xss_patterns + sql_patterns

            def sanitize_value(value: str) -> str:
                cleaned = value
                for pattern, replacement, flags in all_patterns:
                    cleaned = re.sub(pattern, replacement, cleaned, flags=flags)
                # HTML entity encoding for remaining dangerous chars
                cleaned = cleaned.replace("<", "&lt;").replace(">", "&gt;")
                cleaned = cleaned.replace('"', "&quot;").replace("'", "&#x27;")
                return cleaned.strip()

            # If no specific fields, sanitize all string fields
            target_fields = fields_to_sanitize if fields_to_sanitize else [
                k for k, v in data.items() if isinstance(v, str) and not k.startswith("_")
            ]

            for field_name in target_fields:
                if field_name in result_data and isinstance(result_data[field_name], str):
                    original = result_data[field_name]
                    cleaned = sanitize_value(original)
                    if original != cleaned:
                        sanitized[field_name] = {"original_length": len(original), "cleaned_length": len(cleaned)}
                    result_data[field_name] = cleaned

            logger.debug(f"SanitizeBlock: Sanitized {len(sanitized)} fields")
            return {
                "success": True,
                "data": result_data,
                "sanitized_fields": sanitized,
                "sanitized_count": len(sanitized),
            }
        except Exception as e:
            return {"success": False, "error": f"SanitizeBlock: {str(e)}"}
