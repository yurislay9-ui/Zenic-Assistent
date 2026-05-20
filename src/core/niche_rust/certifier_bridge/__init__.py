"""
Zenic-Agents — Blueprint Certifier Bridge (Phase 6.D)

Python wrapper for the Rust-compiled blueprint certification engine
exposed via PyO3 in the ``_zenic_native`` extension module.

Provides:
    - BlueprintCertifier: convert templates → BlueprintConfig → CertifiedBlueprint
    - CertificationHelper: convenience methods for common certification workflows
    - CertificationResultPy: Python-side result wrapper

Fallback:
    If the Rust extension is not available (e.g., during development
    without maturin build), all methods return None/empty with a
    logged warning. This ensures the codebase never crashes due
    to a missing native extension.
"""

from ._types import CertificationResultPy, NATIVE_AVAILABLE
from ._mixin_core import BlueprintCertifier, CertificationHelper

__all__ = [
    "CertificationResultPy",
    "BlueprintCertifier",
    "CertificationHelper",
    "NATIVE_AVAILABLE",
]
