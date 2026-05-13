"""
ZENIC-AGENTS - Reflexion Sandbox v16 (Isolated + Symbolic Execution)

Sandbox con ejecucion simbolica acotada real, timeout real, K-Path limiting
basado en grafo de dependencias, y path pruning para I/O.
"""

from .sandbox import ReflexionSandbox
from ._imports import (
    SandboxResult, TimeoutEnforcer, SymbolicExecutor, KPathAnalyzer
)

__all__ = [
    "ReflexionSandbox",
    "SandboxResult",
    "TimeoutEnforcer",
    "SymbolicExecutor",
    "KPathAnalyzer",
]
