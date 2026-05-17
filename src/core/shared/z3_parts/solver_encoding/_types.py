"""
Z3 Solver Encoding Mixin.

Provides domain classification and constraint encoding helpers:
- _classify_domain: Domain type classification (ENUM, NUMERIC_INT, NUMERIC_REAL, BOOLEAN, MIXED)
- _add_enum_constraint: Enum/Mixed constraint encoding
- _add_numeric_constraint: Numeric constraint encoding (FIXED: proper fallback)
- _add_boolean_constraint: Boolean constraint encoding
- _encode_value: Bijective value encoding to integers
- _decode_value: Bijective value decoding from integers
- _reset_encoding: Clear encoding maps to prevent unbounded memory growth

FIX (Phase 2): _add_numeric_constraint fallback was trivially true
(Implies(v1 == v2, True)). Now uses domain-aware sampling with the
constraint's .satisfied() method to build proper Z3 constraints.

FIX (Phase 3): Added _reset_encoding() to prevent unbounded growth of
_encode_map/_decode_map across solver invocations. Added max size limit
with LRU-style eviction when maps exceed _MAX_ENCODE_ENTRIES.
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


