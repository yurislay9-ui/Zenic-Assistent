"""
Niche Rust Bridge — NicheCatalog class.

Query interface for the Rust-compiled niche catalog.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from ._native import NATIVE_AVAILABLE, _native

logger = logging.getLogger(__name__)


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
        """Get all niche definitions from the compiled catalog."""
        if not NATIVE_AVAILABLE:
            logger.warning("NicheCatalog.get_all: Rust extension not available")
            return []
        return _native.catalog_get_all()

    def get_by_id(self, niche_id: str) -> Optional[Any]:
        """Get a niche definition by its niche_id."""
        if not niche_id or not isinstance(niche_id, str):
            logger.error("NicheCatalog.get_by_id: niche_id must be a non-empty string")
            return None
        if not NATIVE_AVAILABLE:
            logger.warning("NicheCatalog.get_by_id: Rust extension not available")
            return None
        return _native.catalog_get_by_id(niche_id)

    def get_by_category(self, category: str) -> List[Any]:
        """Get all niches in a given category."""
        if not NATIVE_AVAILABLE:
            logger.warning("NicheCatalog.get_by_category: Rust extension not available")
            return []
        try:
            cat_enum = getattr(_native, "NicheCategory", None)
            if cat_enum is None:
                return []
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
        """Search niches by text query."""
        if not query or not isinstance(query, str):
            return []
        if not NATIVE_AVAILABLE:
            logger.warning("NicheCatalog.search: Rust extension not available")
            return []
        return _native.catalog_search(query)

    def count(self) -> int:
        """Get the total number of niches in the catalog."""
        if not NATIVE_AVAILABLE:
            return 0
        return _native.catalog_count()

    def ids(self) -> List[str]:
        """Get all niche_id strings from the catalog."""
        if not NATIVE_AVAILABLE:
            return []
        return _native.catalog_ids()

    def categories(self) -> List[str]:
        """Get all available niche category strings."""
        if not NATIVE_AVAILABLE:
            return []
        return _native.get_niche_categories()

    def category_display_names(self) -> List[str]:
        """Get human-readable display names for all categories."""
        if not NATIVE_AVAILABLE:
            return []
        return _native.get_niche_category_display_names()
