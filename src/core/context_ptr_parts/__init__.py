"""
ContextPointerEngine sub-package — Vectorized signature indexing for code paths.
"""

from ._imports import CONTEXT_STORE_ROOT, FunctionSignature
from ._pointer import ContextPointer
from ._index import SignatureIndex

__all__ = [
    "CONTEXT_STORE_ROOT",
    "FunctionSignature",
    "ContextPointer",
    "SignatureIndex",
]
