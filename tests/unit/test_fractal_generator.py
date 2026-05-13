"""
Unit tests for FractalGenerator (Brecha C)

Tests the 3-phase fractal generation pipeline:
  Phase 1 (Structural): Directory tree + file names
  Phase 2 (Skeletons): Empty classes/functions with docstrings
  Phase 3 (Fill): Logic implementation item by item

Also tests project templates and fallback generation.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.fractal_generator import FractalGenerator


# No fixtures needed here since test classes create FractalGenerator() in setup_method

from .test_fractal_parts import *  # noqa: F401,F403
