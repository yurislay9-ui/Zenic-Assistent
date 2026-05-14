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

from ._types import (
    _MAX_EXHAUSTIVE_PAIRS, _MAX_ENCODE_ENTRIES, _EVICT_BATCH_SIZE,
    _DEFAULT_MAX_SAMPLES, _REAL_DECIMAL_PRECISION,
)

try:
    import z3 as z3_module
    _HAS_Z3 = True
except ImportError:
    z3_module = None
    _HAS_Z3 = False

logger = logging.getLogger(__name__)


from ._constraints import Z3ConstraintMixin


class Z3SolverEncodingMixin(Z3ConstraintMixin):
    """Mixin for domain classification and Z3 constraint encoding helpers."""

    # ================================================================
    #  Domain classification
    # ================================================================

    def _classify_domain(self, values):
        """
        Classify a domain into its Z3-native type.

        Returns one of: 'ENUM', 'NUMERIC_INT', 'NUMERIC_REAL', 'BOOLEAN', 'MIXED'
        """
        if not values:
            return "ENUM"

        has_int = False
        has_float = False
        has_bool = False
        has_str = False
        has_other = False

        for v in values:
            if isinstance(v, bool):
                has_bool = True
            elif isinstance(v, int):
                has_int = True
            elif isinstance(v, float):
                has_float = True
            elif isinstance(v, str):
                has_str = True
            else:
                has_other = True

        # Pure boolean
        if has_bool and not has_int and not has_float and not has_str and not has_other:
            return "BOOLEAN"

        # Pure numeric
        if (has_int or has_float) and not has_str and not has_bool and not has_other:
            if has_float:
                return "NUMERIC_REAL"
            return "NUMERIC_INT"

        # Pure string / enum
        if has_str and not has_int and not has_float and not has_bool and not has_other:
            return "ENUM"

        # Anything else -> mixed
        return "MIXED"

    # ================================================================
    #  Constraint encoding helpers
