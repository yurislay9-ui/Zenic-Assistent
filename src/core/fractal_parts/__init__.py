"""
ZENIC-AGENTS - FractalGenerator v16

Sub-package for fractal code generation.

Re-exports all public symbols for backward compatibility.
"""

from .types import FileBlueprint, FractalSpec, FractalResult
from .structure import PROJECT_TEMPLATES, DEFAULT_TEMPLATE
from .generator import FractalGenerator

__all__ = [
    "FileBlueprint",
    "FractalSpec",
    "FractalResult",
    "FractalGenerator",
    "PROJECT_TEMPLATES",
    "DEFAULT_TEMPLATE",
]
