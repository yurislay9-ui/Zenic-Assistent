"""Shared fixtures for FractalGenerator tests."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.fractal_generator import FractalGenerator


# No shared fixtures needed; each test class creates its own FractalGenerator()
# via setup_method. This conftest.py exists for future shared fixture additions.
