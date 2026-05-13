"""
Unit tests for Z3Solver

Tests the Z3 SMT Solver wrapper with conditional Z3 import.
Tests should work with or without Z3 installed.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.shared.z3_solver import Z3Solver


# ============================================================
#  Fixtures (shared with sub-modules)
# ============================================================

@pytest.fixture
def solver():
    """Create a Z3Solver with default timeout."""
    return Z3Solver(timeout_ms=5000)


@pytest.fixture
def short_timeout_solver():
    """Create a Z3Solver with very short timeout for timeout tests."""
    return Z3Solver(timeout_ms=500)


from .test_z3_parts import *  # noqa: F401,F403
