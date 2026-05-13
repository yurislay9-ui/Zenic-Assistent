"""
ZENIC-AGENTS - SemanticEngine (Facade)

Thin facade — all logic lives in semantic_parts/.
"""

from .semantic_parts import *  # noqa: F401,F403
from .semantic_parts import SemanticEngine, SemanticResult

__all__ = [
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "INTENT_PROTOTYPES",
    "GOAL_PROTOTYPES",
    "SemanticResult",
    "SemanticEngine",
]
