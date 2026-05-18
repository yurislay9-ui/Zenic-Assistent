"""
Helper functions for InteractiveDataCollector — template extraction, progress
calculation, field validation, and answer application.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ._constants import FIELD_SUGGESTIONS, FIELD_VALIDATORS, MAX_ANSWER_LENGTH
from ._types import CompletionSession


def extract_questions_from_template(
    template_dict: Dict[str, Any], session: CompletionSession,
) -> List[Dict[str, Any]]:
    """Extract questions for missing required fields from template."""
    questions: List[Dict[str, Any]] = []
    template = template_dict.get("template", template_dict)
    sections = template.get("sections", {})

    for section_id, section in sections.items():
        if not isinstance(section, dict):
            continue
        fields = section.get("fields", {})
        for field_name, field_def in fields.items():
            if not isinstance(field_def, dict):
                continue
            # Skip already answered fields
            if field_name in session.answers:
                continue
            # Skip non-required fields that have defaults
            is_required = field_def.get("required", False)
            if not is_required and field_def.get("default") is not None:
                continue
            questions.append({
                "field_name": field_name,
                "display_name": field_def.get("display_name", field_name.replace("_", " ").title()),
                "field_type": field_def.get("type", "text"),
                "section_id": section_id,
                "description": field_def.get("description", ""),
                "is_required": is_required,
                "order": field_def.get("order", len(questions)),
                "suggestions": FIELD_SUGGESTIONS.get(field_name, field_def.get("suggestions", [])),
                "enum_variants": field_def.get("enum", []),
                "default_value": field_def.get("default"),
                "validation_hint": field_def.get("validation_hint", ""),
            })

    # Sort: required first, then by order
    questions.sort(key=lambda q: (not q["is_required"], q["order"]))
    return questions


def calculate_progress(
    template_dict: Dict[str, Any], session: CompletionSession,
) -> Dict[str, Any]:
    """Calculate completion progress from template and session answers."""
    template = template_dict.get("template", template_dict)
    sections = template.get("sections", {})

    total_fields = 0
    filled_fields = 0
    missing_required = 0

    for section_id, section in sections.items():
        if not isinstance(section, dict):
            continue
        fields = section.get("fields", {})
        for field_name, field_def in fields.items():
            if not isinstance(field_def, dict):
                continue
            total_fields += 1
            if field_name in session.answers or field_def.get("default") is not None:
                filled_fields += 1
            elif field_def.get("required", False):
                missing_required += 1

    completion_pct = (filled_fields / total_fields * 100.0) if total_fields > 0 else 0.0

    return {
        "total_fields": total_fields,
        "filled_fields": filled_fields,
        "missing_required": missing_required,
        "completion_pct": round(completion_pct, 1),
    }


def validate_field_value(
    field_type: str, value: str, enum_variants: List[str],
) -> bool:
    """Validate a field value by type (deterministic)."""
    if not value or len(value) > MAX_ANSWER_LENGTH:
        return False

    # Enum validation
    if enum_variants and field_type == "enum":
        return value in enum_variants

    # Type-specific validation
    validator = FIELD_VALIDATORS.get(field_type)
    if validator is not None:
        try:
            return validator(value)
        except Exception:
            return False

    # Default: non-empty string
    return len(value.strip()) > 0


def apply_answer_to_template(
    template_dict: Dict[str, Any], field_name: str, value: str,
) -> None:
    """Apply an answer to the template dict in-place."""
    template = template_dict.get("template", template_dict)
    sections = template.get("sections", {})

    for section_id, section in sections.items():
        if not isinstance(section, dict):
            continue
        fields = section.get("fields", {})
        if field_name in fields:
            if isinstance(fields[field_name], dict):
                fields[field_name]["value"] = value
            else:
                fields[field_name] = value
            break
