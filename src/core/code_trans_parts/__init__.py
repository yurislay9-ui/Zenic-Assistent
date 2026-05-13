"""
Code Transformer - Refactoring, bug fixing, and optimization.

Applies real transformations to code based on AST analysis and solver insights:
- Python refactoring with type annotations
- Python bug fixing (resource leaks, missing returns, etc.)
- Function optimization with guard clauses
"""

from .transformer import CodeTransformer

__all__ = ["CodeTransformer"]
