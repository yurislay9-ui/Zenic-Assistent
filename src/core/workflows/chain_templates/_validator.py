"""
ZENIC-AGENTS — Chain template search and validation functions.

Provides event-based and intent-based template discovery, extracted
from ChainTemplateLibrary for modularity.
"""

from __future__ import annotations

from ._types import ChainTemplate


# ---------------------------------------------------------------------------
#  Search helpers
# ---------------------------------------------------------------------------


def find_templates_for_event(
    templates: dict[str, ChainTemplate],
    event_type: str,
) -> list[ChainTemplate]:
    """Find templates whose event_patterns match the given event_type.

    Matching is case-insensitive substring: if the event_type contains
    any of the template's event_patterns (or vice-versa), it matches.

    Args:
        templates: The template dictionary to search.
        event_type: The event type string to match against.

    Returns:
        Sorted list of matching ChainTemplate instances.
    """
    results: list[ChainTemplate] = []
    event_lower = event_type.lower()
    for template in templates.values():
        for pattern in template.event_patterns:
            if pattern.lower() in event_lower or event_lower in pattern.lower():
                results.append(template)
                break
    return sorted(results, key=lambda t: t.name)


def find_templates_for_intent(
    templates: dict[str, ChainTemplate],
    intent: str,
) -> list[ChainTemplate]:
    """Find templates by keyword matching against intent_keywords.

    A template matches if any of its intent_keywords appear in the
    intent string (case-insensitive).

    Args:
        templates: The template dictionary to search.
        intent: The intent string to search within.

    Returns:
        Sorted list of matching ChainTemplate instances (most keywords first).
    """
    results: list[ChainTemplate] = []
    intent_lower = intent.lower()
    for template in templates.values():
        for keyword in template.intent_keywords:
            if keyword.lower() in intent_lower:
                results.append(template)
                break
    return sorted(results, key=lambda t: len(t.intent_keywords), reverse=True)
