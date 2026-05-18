"""
Zenic-Agents — Niche Rust Bridge (Phase 6.A)

Python wrapper for the Rust-compiled niche system exposed
via PyO3 in the ``_zenic_native`` extension module.

Provides:
    - NicheCatalog: query the compiled niche catalog (24 niches)
    - NicheTemplate: generate, validate, fill YAML templates
    - NicheBridge: unified facade for both systems
    - get_bridge: singleton factory function

Fallback:
    If the Rust extension is not available (e.g., during development
    without maturin build), all methods return None/empty with a
    logged warning. This ensures the codebase never crashes due
    to a missing native extension.
"""

from ._native import NATIVE_AVAILABLE
from ._catalog import NicheCatalog
from ._template import NicheTemplate
from ._core import NicheBridge, get_bridge

__all__ = [
    "NicheCatalog",
    "NicheTemplate",
    "NicheBridge",
    "get_bridge",
    "NATIVE_AVAILABLE",
]
