"""
A33 AutomationNamer — SINGLE RESPONSIBILITY: Generate descriptive name for automation.

Deterministic template composition. No AI.
Generates a descriptive name and URL-safe slug from the trigger spec,
action spec, and context of an automation.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from ..resilience import BaseAgent
from ..schemas import AutoDescription, TriggerSpec, ActionSpec, NameResult

# ──────────────────────────────────────────────────────────────
# STOP WORDS — EN + ES (removed from name generation)
# ──────────────────────────────────────────────────────────────

STOP_WORDS = {
    # Spanish
    "un", "una", "el", "la", "los", "las", "a", "de", "del",
    "en", "por", "para", "con", "que", "se", "su", "al",
    "lo", "le", "les", "y", "o", "es", "son", "fue", "ser",
    # English
    "the", "a", "an", "is", "are", "was", "were", "be",
    "create", "make", "generate", "build", "automate", "set",
    "get", "put", "do", "run", "go", "has", "have", "had",
    "this", "that", "these", "those", "it", "its",
    "from", "into", "with", "without", "by", "to", "of",
    "and", "or", "but", "not", "in", "on", "at",
}

# Name templates by trigger + action combination
NAME_TEMPLATES = {
    ("schedule", "email"): "scheduled_email_{detail}",
    ("schedule", "report"): "scheduled_report_{detail}",
    ("schedule", "db"): "scheduled_backup_{detail}",
    ("schedule", "notification"): "scheduled_alert_{detail}",
    ("event", "notification"): "event_alert_{detail}",
    ("event", "http"): "event_webhook_{detail}",
    ("webhook", "transform"): "webhook_processor_{detail}",
    ("webhook", "db"): "webhook_persister_{detail}",
    ("webhook", "notification"): "webhook_notifier_{detail}",
}


class AutomationNamer(BaseAgent[NameResult]):
    """
    A33: Generate descriptive name for automation.

    Single Responsibility: Name generation ONLY.
    Method: Template composition + keyword extraction (deterministic).
    Fallback: Return "automation_{timestamp}".
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A33_AutomationNamer", **kwargs)

    def execute(self, input_data: Any) -> NameResult:
        """
        Generate name from trigger, action, and context.

        input_data should be a dict with:
          - 'trigger_spec': TriggerSpec (optional)
          - 'action_spec': ActionSpec (optional)
          - 'description': str (optional)
          - 'context': dict (optional)
        Or an AutoDescription object.
        """
        if isinstance(input_data, AutoDescription):
            return self._name_from_description(input_data.description)

        if not isinstance(input_data, dict):
            return self.fallback(input_data)

        trigger_spec = input_data.get("trigger_spec")
        action_spec = input_data.get("action_spec")
        description = input_data.get("description", "")

        # If we have specs, use template composition
        if trigger_spec or action_spec:
            return self._name_from_specs(
                trigger_spec, action_spec, description
            )

        # If only description, extract name from it
        if description:
            return self._name_from_description(description)

        return self.fallback(input_data)

    def _name_from_specs(
        self,
        trigger_spec: Any,
        action_spec: Any,
        description: str,
    ) -> NameResult:
        """Generate name from trigger + action specs using templates."""
        trigger_type = ""
        action_type = ""

        if isinstance(trigger_spec, TriggerSpec):
            trigger_type = trigger_spec.type
        elif isinstance(trigger_spec, dict):
            trigger_type = trigger_spec.get("type", "")

        if isinstance(action_spec, ActionSpec):
            action_type = action_spec.type
        elif isinstance(action_spec, dict):
            action_type = action_spec.get("type", "")

        # Try template lookup
        key = (trigger_type, action_type)
        template = NAME_TEMPLATES.get(key)

        if template:
            detail = self._extract_detail(description, max_words=2)
            name = template.format(detail=detail)
        else:
            # Compose from parts
            parts = []
            if trigger_type:
                parts.append(trigger_type)
            if action_type:
                parts.append(action_type)
            detail = self._extract_detail(description, max_words=1)
            if detail:
                parts.append(detail)
            name = "_".join(parts) if parts else "automation"

        slug = self._to_slug(name)

        return NameResult(
            name=name,
            slug=slug,
            source="deterministic",
        )

    def _name_from_description(self, description: str) -> NameResult:
        """Generate name from description text alone."""
        # Extract meaningful words
        words = re.sub(r"[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ\s]", "", description).split()

        # Filter stop words and take first 4 meaningful words
        meaningful = [
            w.lower() for w in words[:8]
            if w.lower() not in STOP_WORDS and len(w) > 1
        ][:4]

        if not meaningful:
            name = "automation"
        else:
            name = "_".join(meaningful)

        slug = self._to_slug(name)

        return NameResult(
            name=name,
            slug=slug,
            source="deterministic",
        )

    @staticmethod
    def _extract_detail(description: str, max_words: int = 2) -> str:
        """Extract a short detail phrase from description."""
        if not description:
            return "auto"

        words = re.sub(r"[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ\s]", "", description).split()
        meaningful = [
            w.lower() for w in words[:10]
            if w.lower() not in STOP_WORDS and len(w) > 1
        ][:max_words]

        return "_".join(meaningful) if meaningful else "auto"

    @staticmethod
    def _to_slug(name: str) -> str:
        """Convert name to URL-safe slug."""
        # Normalize unicode
        slug = unicodedata.normalize("NFKD", name)
        # Remove non-ASCII
        slug = slug.encode("ascii", "ignore").decode("ascii")
        # Lowercase
        slug = slug.lower()
        # Replace non-alphanumeric with hyphens
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        # Remove leading/trailing hyphens
        slug = slug.strip("-")
        # Collapse multiple hyphens
        slug = re.sub(r"-+", "-", slug)
        return slug

    def fallback(self, input_data: Any) -> NameResult:
        """Fallback: Return generic automation name with deterministic ID."""
        from src.core.shared.deterministic import FencingTokenGenerator
        _namer_fencing = FencingTokenGenerator("automation_namer")
        ts = _namer_fencing.next() % 100000
        return NameResult(
            name=f"automation_{ts}",
            slug=f"automation-{ts}",
            source="fallback",
        )
