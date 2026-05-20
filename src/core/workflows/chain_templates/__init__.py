"""
ZENIC-AGents — ChainTemplateLibrary: Reusable workflow templates.

Manages a library of chain templates that can be instantiated with
variable substitution to produce concrete ComposedChain instances.

Built-in templates cover common PYME workflows:
  1. detect_validate_notify
  2. detect_validate_create_task_escalate
  3. low_stock_chain
  4. invoice_overdue_chain
  5. data_import_chain

Thread-safe via RLock. Persisted to SQLite (chain_templates.sqlite).

This package re-exports all public symbols from its sub-modules so that
``from src.core.workflows.chain_templates import ...`` continues to work
exactly as before the split.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

# Re-export types so they are importable from this package
from ._types import (  # noqa: F401 — re-exports
    ChainTemplate,
    TemplateStep,
    TemplateVariable,
    TemplateCategory,
    _substitute_value,
    _DB_DIR,
    _DB_PATH,
)

from ._loader import (  # noqa: F401 — used internally
    init_db,
    load_templates_from_db,
    save_template_to_db,
    delete_template_from_db,
    serialize_steps,
    deserialize_steps,
    serialize_variables,
    deserialize_variables,
)

from ._renderer import (  # noqa: F401 — used internally
    get_builtin_definitions,
    instantiate_template,
)

from ._validator import (  # noqa: F401 — used internally
    find_templates_for_event,
    find_templates_for_intent,
)

from ._types import logger  # noqa: E402


# ---------------------------------------------------------------------------
#  ChainTemplateLibrary
# ---------------------------------------------------------------------------


class ChainTemplateLibrary:
    """Library of reusable workflow templates with SQLite persistence.

    Thread-safe via RLock. Singleton via get_template_library().
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._templates: dict[str, ChainTemplate] = {}
        init_db()
        self._templates = load_templates_from_db()
        self._register_builtins()
        logger.info("ChainTemplateLibrary initialized with %d templates", len(self._templates))

    # ------------------------------------------------------------------
    #  CRUD
    # ------------------------------------------------------------------

    def register_template(self, template: ChainTemplate) -> str:
        """Register a new template. Returns the template_id.

        If template.template_id is empty, a UUID is generated.
        """
        with self._lock:
            if not template.template_id:
                template.template_id = f"tpl_{uuid.uuid4().hex[:12]}"
            if not template.created_at:
                template.created_at = time.time()
            self._templates[template.template_id] = template
            save_template_to_db(template)
            logger.info("Registered template %s: %s", template.template_id, template.name)
            return template.template_id

    def unregister_template(self, template_id: str) -> bool:
        """Remove a template by ID. Returns True if found and removed."""
        with self._lock:
            if template_id not in self._templates:
                logger.warning("Template %s not found for removal", template_id)
                return False
            del self._templates[template_id]
            delete_template_from_db(template_id)
            logger.info("Unregistered template %s", template_id)
            return True

    def get_template(self, template_id: str) -> ChainTemplate | None:
        """Retrieve a template by ID."""
        with self._lock:
            return self._templates.get(template_id)

    def list_templates(self, category: str | None = None) -> list[ChainTemplate]:
        """List all templates, optionally filtered by category."""
        with self._lock:
            templates = list(self._templates.values())
        if category is not None:
            templates = [t for t in templates if t.category == category]
        return sorted(templates, key=lambda t: t.name)

    # ------------------------------------------------------------------
    #  Search
    # ------------------------------------------------------------------

    def find_templates_for_event(self, event_type: str) -> list[ChainTemplate]:
        """Find templates whose event_patterns match the given event_type."""
        with self._lock:
            return find_templates_for_event(self._templates, event_type)

    def find_templates_for_intent(self, intent: str) -> list[ChainTemplate]:
        """Find templates by keyword matching against intent_keywords."""
        with self._lock:
            return find_templates_for_intent(self._templates, intent)

    # ------------------------------------------------------------------
    #  Instantiation
    # ------------------------------------------------------------------

    def instantiate(self, template_id: str, variables: dict[str, Any]) -> Any:
        """Create a concrete ComposedChain from a template with variable substitution.

        Raises KeyError if the template does not exist.
        Raises ValueError if a required variable is missing.
        """
        with self._lock:
            template = self._templates.get(template_id)
            if template is None:
                raise KeyError(f"Template '{template_id}' not found")

        # Delegates to the standalone renderer function (runs outside lock
        # because instantiation is read-only w.r.t. the template dict).
        return instantiate_template(template_id, template, variables)

    # ------------------------------------------------------------------
    #  Built-in templates
    # ------------------------------------------------------------------

    def _register_builtins(self) -> None:
        """Register the five built-in templates if not already present."""
        builtins = get_builtin_definitions()
        for btpl in builtins:
            if btpl.template_id not in self._templates:
                self._templates[btpl.template_id] = btpl
                save_template_to_db(btpl, is_builtin=True)
            # else: already loaded from DB

    # Backward-compatible aliases (original class had these as static methods)
    _builtin_definitions = staticmethod(get_builtin_definitions)
    _serialize_steps = staticmethod(serialize_steps)
    _deserialize_steps = staticmethod(deserialize_steps)
    _serialize_variables = staticmethod(serialize_variables)
    _deserialize_variables = staticmethod(deserialize_variables)


# ---------------------------------------------------------------------------
#  Singleton
# ---------------------------------------------------------------------------

_instance: ChainTemplateLibrary | None = None
_instance_lock = threading.Lock()


def get_template_library() -> ChainTemplateLibrary:
    """Return the ChainTemplateLibrary singleton (thread-safe)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ChainTemplateLibrary()
    return _instance


__all__ = [
    "ChainTemplate",
    "TemplateStep",
    "TemplateVariable",
    "TemplateCategory",
    "ChainTemplateLibrary",
    "get_template_library",
]
