"""
Z3 Solver Sub-Package.

Modular decomposition of the Z3 SMT Solver wrapper.

Re-exports all public symbols for backward compatibility.
"""

from .solver import Z3Solver, HAS_Z3
from .null_safety import Z3NullSafetyMixin
from .type_safety import Z3TypeSafetyMixin
from .type_lattice import Z3TypeLatticeMixin
from .invariants import Z3InvariantMixin
from .invariants_patterns import Z3InvariantPatternsMixin
from .solver_core import Z3SolverCoreMixin
from .solver_encoding import Z3SolverEncodingMixin
from .ac3_fallback import AC3FallbackMixin
from .z3_context import z3_session

__all__ = [
    "Z3Solver",
    "HAS_Z3",
    "Z3NullSafetyMixin",
    "Z3TypeSafetyMixin",
    "Z3TypeLatticeMixin",
    "Z3InvariantMixin",
    "Z3InvariantPatternsMixin",
    "Z3SolverCoreMixin",
    "Z3SolverEncodingMixin",
    "AC3FallbackMixin",
    "z3_session",
]
