"""
Niche Rust Bridge — FFI import block.

Shared Rust extension import for all bridge sub-modules.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
#  Rust Extension Import
# ──────────────────────────────────────────────────────────────

NATIVE_AVAILABLE: bool = False
_native = None

try:
    import _zenic_native as _native  # type: ignore[import-not-found]
    NATIVE_AVAILABLE = True
except ImportError:
    logger.warning(
        "NicheRust: _zenic_native extension not available. "
        "Run 'maturin develop' to build the Rust extension. "
        "Falling back to no-op mode."
    )
