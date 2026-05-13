"""
Code Generator - Pipeline-driven and contextual code generation.

Genera codigo usando datos del AST, solver y MCTS.
Incluye generacion contextual para Python, Kotlin, Go, y JavaScript.
"""

from .code_gen_parts import *  # noqa: F401,F403
from .code_gen_parts import CodeGenerator  # explicit

__all__ = ["CodeGenerator"]
