"""Shared fixtures for Z3Solver tests."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.shared.z3_solver import Z3Solver


@pytest.fixture
def solver():
    """Create a Z3Solver with default timeout."""
    return Z3Solver(timeout_ms=5000)


@pytest.fixture
def short_timeout_solver():
    """Create a Z3Solver with very short timeout for timeout tests."""
    return Z3Solver(timeout_ms=500)
