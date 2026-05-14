"""
Zenic-Agents — Niche Rust Bridge (Phase 6.A)

Python wrapper for the Rust-compiled niche system exposed
via PyO3 in the ``_zenic_native`` extension module.

Provides:
    - NicheCatalog: query the compiled niche catalog (24 niches)
    - NicheTemplate: generate, validate, fill YAML templates
    - NicheBridge: unified facade for both systems

Fallback:
    If the Rust extension is not available (e.g., during development
    without maturin build), all methods return None/empty with a
    logged warning. This ensures the codebase never crashes due
    to a missing native extension.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
#  Rust Extension Import
# ──────────────────────────────────────────────────────────────

_NATIVE_AVAILABLE: bool = False
_native = None

try:
    import _zenic_native as _native  # type: ignore[import-not-found]
    _NATIVE_AVAILABLE = True
except ImportError:
    logger.warning(
        "NicheRust: _zenic_native extension not available. "
        "Run 'maturin develop' to build the Rust extension. "
        "Falling back to no-op mode."
    )


# ──────────────────────────────────────────────────────────────
#  NicheCatalog — Query the compiled niche catalog
# ──────────────────────────────────────────────────────────────

class NicheCatalog:
    """Query interface for the Rust-compiled niche catalog.

    The catalog contains 24 cutting-edge niches organized into
    7 categories. All data is compiled into the Rust binary —
    no YAML files, no filesystem access.

    Usage::

        catalog = NicheCatalog()

        # List all niches
        all_niches = catalog.get_all()

        # Get a specific niche
        niche = catalog.get_by_id("telemedicine")

        # Filter by category
        health_niches = catalog.get_by_category("healthtech")

        # Search
        results = catalog.search("blockchain")

        # List all IDs
        ids = catalog.ids()
    """

    def get_all(self) -> List[Any]:
        """Get all niche definitions from the compiled catalog.

        Returns:
            List of NicheDefinition objects (PyO3), or empty list
            if the Rust extension is not available.
        """
        if not _NATIVE_AVAILABLE:
            logger.warning("NicheCatalog.get_all: Rust extension not available")
            return []
        return _native.catalog_get_all()

    def get_by_id(self, niche_id: str) -> Optional[Any]:
        """Get a niche definition by its niche_id.

        Args:
            niche_id: The unique identifier (e.g., "telemedicine").

        Returns:
            NicheDefinition object if found, None otherwise.
        """
        if not niche_id or not isinstance(niche_id, str):
            logger.error("NicheCatalog.get_by_id: niche_id must be a non-empty string")
            return None
        if not _NATIVE_AVAILABLE:
            logger.warning("NicheCatalog.get_by_id: Rust extension not available")
            return None
        return _native.catalog_get_by_id(niche_id)

    def get_by_category(self, category: str) -> List[Any]:
        """Get all niches in a given category.

        Args:
            category: Category string (e.g., "healthtech", "fintech").
                Must match one of the 7 NicheCategory values.

        Returns:
            List of NicheDefinition objects, or empty list.
        """
        if not _NATIVE_AVAILABLE:
            logger.warning("NicheCatalog.get_by_category: Rust extension not available")
            return []
        try:
            cat_enum = getattr(_native, "NicheCategory", None)
            if cat_enum is None:
                return []
            # Try to convert string to enum
            category_map = {
                "ai_data": cat_enum.AiData if hasattr(cat_enum, "AiData") else None,
                "fintech": cat_enum.FinTech if hasattr(cat_enum, "FinTech") else None,
                "healthtech": cat_enum.HealthTech if hasattr(cat_enum, "HealthTech") else None,
                "greentech": cat_enum.GreenTech if hasattr(cat_enum, "GreenTech") else None,
                "edtech": cat_enum.EdTech if hasattr(cat_enum, "EdTech") else None,
                "proptech": cat_enum.PropTech if hasattr(cat_enum, "PropTech") else None,
                "legaltech": cat_enum.LegalTech if hasattr(cat_enum, "LegalTech") else None,
            }
            cat_value = category_map.get(category.lower())
            if cat_value is None:
                logger.error("NicheCatalog: Unknown category '%s'", category)
                return []
            return _native.catalog_get_by_category(cat_value)
        except Exception as e:
            logger.error("NicheCatalog.get_by_category: %s", e)
            return []

    def search(self, query: str) -> List[Any]:
        """Search niches by text query.

        Searches across name, domain, subdomain, and tags.

        Args:
            query: Search string (case-insensitive).

        Returns:
            List of matching NicheDefinition objects.
        """
        if not query or not isinstance(query, str):
            return []
        if not _NATIVE_AVAILABLE:
            logger.warning("NicheCatalog.search: Rust extension not available")
            return []
        return _native.catalog_search(query)

    def count(self) -> int:
        """Get the total number of niches in the catalog.

        Returns:
            Integer count (24 when Rust extension is available).
        """
        if not _NATIVE_AVAILABLE:
            return 0
        return _native.catalog_count()

    def ids(self) -> List[str]:
        """Get all niche_id strings from the catalog.

        Returns:
            List of niche_id strings.
        """
        if not _NATIVE_AVAILABLE:
            return []
        return _native.catalog_ids()

    def categories(self) -> List[str]:
        """Get all available niche category strings.

        Returns:
            List of category strings (e.g., ["ai_data", "fintech", ...]).
        """
        if not _NATIVE_AVAILABLE:
            return []
        return _native.get_niche_categories()

    def category_display_names(self) -> List[str]:
        """Get human-readable display names for all categories.

        Returns:
            List of display name strings.
        """
        if not _NATIVE_AVAILABLE:
            return []
        return _native.get_niche_category_display_names()


# ──────────────────────────────────────────────────────────────
#  NicheTemplate — YAML template generation & validation
# ──────────────────────────────────────────────────────────────

class NicheTemplate:
    """YAML template generation and validation system.

    Generates a structured template skeleton from a NicheDefinition,
    validates completeness, and tracks missing fields for the
    interactive data collection agent.

    Usage::

        tmpl = NicheTemplate()

        # Generate a template from a niche
        template = tmpl.generate("telemedicine")

        # Fill a field
        tmpl.set_field(template, "business_identity", "business_name", "My Clinic")

        # Validate
        result = tmpl.validate(template)

        # List missing fields
        missing = tmpl.missing_fields(template)

        # Export to YAML
        yaml_str = tmpl.to_yaml(template)
    """

    def generate(self, niche_id: str) -> Optional[Dict[str, Any]]:
        """Generate a YAML template skeleton from a niche_id.

        Creates a template dict with all fields set to null,
        ready for the interactive agent to fill in.

        Args:
            niche_id: The niche identifier from the catalog.

        Returns:
            Template dict with structure:
            {
                "template": {
                    "metadata": { ... },
                    "sections": { ... },
                    "completeness": { ... }
                }
            }
            Returns None if niche_id not found.
        """
        if not niche_id or not isinstance(niche_id, str):
            logger.error("NicheTemplate.generate: niche_id must be a non-empty string")
            return None
        if not _NATIVE_AVAILABLE:
            logger.warning("NicheTemplate.generate: Rust extension not available")
            return None
        return _native.template_generate(niche_id)

    def generate_from_niche(self, niche: Any) -> Optional[Dict[str, Any]]:
        """Generate a template from an existing NicheDefinition object.

        Args:
            niche: A NicheDefinition object (from catalog queries).

        Returns:
            Template dict, or None on error.
        """
        if niche is None:
            logger.error("NicheTemplate.generate_from_niche: niche cannot be None")
            return None
        if not _NATIVE_AVAILABLE:
            logger.warning("NicheTemplate.generate_from_niche: Rust extension not available")
            return None
        try:
            return _native.template_generate_from_niche(niche)
        except Exception as e:
            logger.error("NicheTemplate.generate_from_niche: %s", e)
            return None

    def validate(self, template_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a template dict for completeness.

        Args:
            template_dict: The template dict (as returned by generate).

        Returns:
            Validation result dict with keys:
            - valid (bool): True if all required fields filled
            - total_fields (int): Total field count
            - filled_fields (int): Fields with values
            - missing_required (int): Required fields without values
            - completion_pct (float): 0.0-100.0
            - status (str): "complete", "partial", or "incomplete"
            - missing_field_names (list[str]): Missing required field names
        """
        if not template_dict:
            return {
                "valid": False,
                "total_fields": 0,
                "filled_fields": 0,
                "missing_required": 0,
                "completion_pct": 0.0,
                "status": "incomplete",
                "missing_field_names": [],
            }
        if not _NATIVE_AVAILABLE:
            logger.warning("NicheTemplate.validate: Rust extension not available")
            return {
                "valid": False,
                "error": "Rust extension not available",
                "total_fields": 0,
                "filled_fields": 0,
                "missing_required": 0,
                "completion_pct": 0.0,
                "status": "incomplete",
                "missing_field_names": [],
            }
        try:
            return _native.template_validate(template_dict)
        except Exception as e:
            logger.error("NicheTemplate.validate: %s", e)
            return {
                "valid": False,
                "error": str(e),
                "total_fields": 0,
                "filled_fields": 0,
                "missing_required": 0,
                "completion_pct": 0.0,
                "status": "incomplete",
                "missing_field_names": [],
            }

    def missing_fields(self, template_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """List all missing required fields in a template.

        This is the primary function used by the interactive agent
        to determine what data to ask the user for next.

        Args:
            template_dict: The template dict.

        Returns:
            List of dicts, each with:
            - name (str): Field name
            - display_name (str): Human-readable name
            - type (str): Field type string
            - section (str): Section ID
            - description (str): Field description
        """
        if not template_dict:
            return []
        if not _NATIVE_AVAILABLE:
            logger.warning("NicheTemplate.missing_fields: Rust extension not available")
            return []
        try:
            return _native.template_missing_fields(template_dict)
        except Exception as e:
            logger.error("NicheTemplate.missing_fields: %s", e)
            return []

    def set_field(
        self,
        template_dict: Dict[str, Any],
        section_id: str,
        field_name: str,
        value: Any,
    ) -> bool:
        """Fill a field value in a template dict.

        Also recalculates completeness after setting the value.

        Args:
            template_dict: The template dict (modified in-place).
            section_id: The section containing the field.
            field_name: The field name to set.
            value: The value to set.

        Returns:
            True if the field was found and set, False otherwise.
        """
        if not template_dict:
            logger.error("NicheTemplate.set_field: template_dict is empty")
            return False
        if not section_id or not field_name:
            logger.error("NicheTemplate.set_field: section_id and field_name required")
            return False
        if not _NATIVE_AVAILABLE:
            logger.warning("NicheTemplate.set_field: Rust extension not available")
            return False
        try:
            return _native.template_set_field(
                template_dict, section_id, field_name, value
            )
        except Exception as e:
            logger.error("NicheTemplate.set_field: %s", e)
            return False

    def to_yaml(self, template_dict: Dict[str, Any]) -> Optional[str]:
        """Serialize a template dict to a YAML string.

        Falls back to JSON if PyYAML is not installed.

        Args:
            template_dict: The template dict.

        Returns:
            YAML (or JSON) string, or None on error.
        """
        if not template_dict:
            return None
        if not _NATIVE_AVAILABLE:
            logger.warning("NicheTemplate.to_yaml: Rust extension not available")
            return None
        try:
            return _native.template_to_yaml(template_dict)
        except Exception as e:
            logger.error("NicheTemplate.to_yaml: %s", e)
            return None


# ──────────────────────────────────────────────────────────────
#  NicheBridge — Unified facade
# ──────────────────────────────────────────────────────────────

class NicheBridge:
    """Unified facade for the Rust niche system.

    Combines NicheCatalog and NicheTemplate into a single
    interface for convenience.

    Usage::

        bridge = NicheBridge()

        # List all niches
        niches = bridge.list_niches()

        # Generate a template
        template = bridge.create_template("telemedicine")

        # Fill fields
        bridge.fill_field(template, "business_identity", "business_name", "My Clinic")

        # Check status
        status = bridge.template_status(template)

        # Get next question for user
        next_question = bridge.next_missing_field(template)
    """

    def __init__(self) -> None:
        self._catalog = NicheCatalog()
        self._template = NicheTemplate()

    # ── Catalog Operations ────────────────────────────────

    def list_niches(self) -> List[Any]:
        """List all available niches from the catalog."""
        return self._catalog.get_all()

    def list_niche_ids(self) -> List[str]:
        """List all niche_id strings."""
        return self._catalog.ids()

    def list_categories(self) -> List[str]:
        """List all niche categories."""
        return self._catalog.categories()

    def get_niche(self, niche_id: str) -> Optional[Any]:
        """Get a specific niche by ID."""
        return self._catalog.get_by_id(niche_id)

    def search_niches(self, query: str) -> List[Any]:
        """Search niches by text."""
        return self._catalog.search(query)

    def niches_by_category(self, category: str) -> List[Any]:
        """Get niches filtered by category."""
        return self._catalog.get_by_category(category)

    def niche_count(self) -> int:
        """Get total niche count."""
        return self._catalog.count()

    # ── Template Operations ───────────────────────────────

    def create_template(self, niche_id: str) -> Optional[Dict[str, Any]]:
        """Generate a YAML template from a niche_id."""
        return self._template.generate(niche_id)

    def validate_template(self, template_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a template for completeness."""
        return self._template.validate(template_dict)

    def fill_field(
        self,
        template_dict: Dict[str, Any],
        section_id: str,
        field_name: str,
        value: Any,
    ) -> bool:
        """Fill a field in the template."""
        return self._template.set_field(
            template_dict, section_id, field_name, value
        )

    def template_status(self, template_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Get validation status of a template."""
        return self._template.validate(template_dict)

    def next_missing_field(self, template_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get the next missing required field for the interactive agent.

        Returns the first missing required field, or None if
        all required fields are filled.

        Args:
            template_dict: The template dict.

        Returns:
            Dict with field info (name, display_name, type, section, description),
            or None if no missing fields.
        """
        missing = self._template.missing_fields(template_dict)
        if not missing:
            return None
        return missing[0]

    def all_missing_fields(self, template_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get all missing required fields."""
        return self._template.missing_fields(template_dict)

    def template_to_yaml(self, template_dict: Dict[str, Any]) -> Optional[str]:
        """Export template to YAML string."""
        return self._template.to_yaml(template_dict)
