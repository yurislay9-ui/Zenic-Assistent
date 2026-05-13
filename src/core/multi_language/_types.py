"""MultiLanguage - Type mappings from YAML to target languages."""

from typing import Dict

# ── Type mapping: YAML → target language ──
TYPE_MAP: Dict[str, Dict[str, str]] = {
    "typescript": {
        "str": "string", "string": "string", "text": "string",
        "int": "number", "integer": "number", "number": "number",
        "float": "number", "decimal": "number", "double": "number",
        "bool": "boolean", "boolean": "boolean",
        "date": "Date", "datetime": "Date",
        "uuid": "string",
        "list": "any[]", "array": "any[]", "json": "any",
        "email": "string", "url": "string", "phone": "string",
    },
    "go": {
        "str": "string", "string": "string", "text": "string",
        "int": "int", "integer": "int", "number": "int",
        "float": "float64", "decimal": "float64", "double": "float64",
        "bool": "bool", "boolean": "bool",
        "date": "time.Time", "datetime": "time.Time",
        "uuid": "string",
        "list": "[]interface{}", "array": "[]interface{}", "json": "map[string]interface{}",
        "email": "string", "url": "string", "phone": "string",
    },
    "kotlin": {
        "str": "String", "string": "String", "text": "String",
        "int": "Int", "integer": "Int", "number": "Int",
        "float": "Double", "decimal": "Double", "double": "Double",
        "bool": "Boolean", "boolean": "Boolean",
        "date": "LocalDate", "datetime": "LocalDateTime",
        "uuid": "UUID",
        "list": "List<Any>", "array": "List<Any>", "json": "Map<String, Any>",
        "email": "String", "url": "String", "phone": "String",
    },
}
