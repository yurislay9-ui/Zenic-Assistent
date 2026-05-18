"""
Z3 Solver Encoding — Constants and type definitions.

Defines tuning constants used by the Z3 constraint encoding mixins:
- _MAX_EXHAUSTIVE_PAIRS: Max domain size for exhaustive pair enumeration
- _MAX_ENCODE_ENTRIES: Max entries in bijective encoding maps before eviction
- _EVICT_BATCH_SIZE: Number of entries to evict when map limit is reached
- _DEFAULT_MAX_SAMPLES: Default max samples for numeric domain sampling
- _REAL_DECIMAL_PRECISION: Decimal precision for Z3 Real value conversion
"""

import logging


try:
    import z3 as z3_module  # type: ignore[import-unresolved]
    _HAS_Z3 = True
except ImportError:
    _HAS_Z3 = False

logger = logging.getLogger(__name__)

# Maximum domain size for exhaustive pair enumeration in numeric fallback
_MAX_EXHAUSTIVE_PAIRS = 500
# Maximum entries in bijective encoding maps before eviction (Phase 3)
_MAX_ENCODE_ENTRIES = 10000
# Number of entries to evict when limit is reached
_EVICT_BATCH_SIZE = 2000
# Default max samples for numeric domain sampling
_DEFAULT_MAX_SAMPLES = 20
# Decimal precision for Z3 Real value conversion
_REAL_DECIMAL_PRECISION = 6


