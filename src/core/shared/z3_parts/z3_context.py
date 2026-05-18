"""
ZENIC-AGENTS — Z3 Session Context Manager.

Eliminates duplicated gc.collect() calls after Z3 operations.
Every Z3 proof/solve method had `gc.collect()` in finally blocks;
this context manager handles it automatically.

NOTE: This context manager is currently available but not yet integrated
into the solver methods (which still use manual reset + gc.collect).
It is intended for future use to replace the scattered gc.collect()
calls in invariants.py and other Z3 solver mixins. When integrating,
replace the manual pattern:
    self._reset_encoding()
    try:
        ...
    finally:
        gc.collect()
with:
    with z3_session(self):
        ...
"""

import gc
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@contextmanager
def z3_session(solver_instance):
    """Context manager for Z3 solver sessions with automatic cleanup.

    Resets Z3 solver state on entry and runs gc.collect() on exit.
    This ensures Z3's internal state is properly garbage collected
    between operations, preventing unbounded memory growth.

    Usage:
        with z3_session(self):
            result = self._z3_solve_attempt(domains, constraints)

    Args:
        solver_instance: The Z3Solver instance (must have _reset_z3_state method).
    """
    try:
        if hasattr(solver_instance, '_reset_z3_state'):
            solver_instance._reset_z3_state()
        yield
    finally:
        gc.collect()
