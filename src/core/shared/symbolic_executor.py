"""
ZENIC-AGENTS - Symbolic Executor v16

Ejecutor Simbolico Acotado real.

Implementa la ejecucion simbolica del Nivel 6 como especifica el documento:
- Estados simbolicos (valores abstractos con constraints)
- Path conditions por cada rama (string + Z3 cuando disponible)
- Path Pruning de side effects (I/O -> Mock)
- K-Path limiting (radio de exploracion)
- Bounded execution (profundidad limitada)
- Assignment tracking (mutaciones de estado simbolico)
- Return value tracking (verificacion de retorno consistente)
- Bounded loop unrolling (hasta 2 iteraciones)
- Violation detection: div-by-zero, index OOB, type mismatch, uninitialized, None deref

This module is now a thin facade that re-exports all public symbols from
the symbolic_parts sub-package for 100% backward compatibility.
"""

from .symbolic_parts import SymbolicValue, SymbolicPath, SymbolicExecutor, HAS_Z3

__all__ = ["SymbolicValue", "SymbolicPath", "SymbolicExecutor", "HAS_Z3"]
