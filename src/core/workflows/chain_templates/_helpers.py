"""
chain_templates._helpers — Variable substitution helper.
"""

from __future__ import annotations

from typing import Any


def substitute_value(value: Any, variables: dict[str, Any]) -> Any:
    """Recursively substitute {{variable}} placeholders in a value."""
    if isinstance(value, str):
        if value.startswith("{{") and value.endswith("}}") and value.count("{{") == 1:
            var_name = value[2:-2].strip()
            if var_name in variables:
                return variables[var_name]
            return value
        result = value
        for var_name, var_value in variables.items():
            placeholder = "{{" + var_name + "}}"
            if placeholder in result:
                result = result.replace(placeholder, str(var_value))
        return result
    if isinstance(value, dict):
        return {k: substitute_value(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute_value(item, variables) for item in value]
    return value
