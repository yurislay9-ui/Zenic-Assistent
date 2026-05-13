"""
ZENIC-AGENTS - Z3 SMT Solver Wrapper v16

Facade module - re-exports from the z3_parts sub-package.

Wrapper del SMT Solver Z3 con import condicional y verificacion
semantica profunda de codigo.

Cuando Z3 esta disponible (pip install z3-solver):
- Verificacion formal real con EnumSort, DataType, cuantificadores
- Null-safety con EnumSort {NONE, SOME_VALUE}
- Type-safety con EnumSort para jerarquia de tipos y compatibilidad
- Invariantes codificadas directamente como constraints Z3
- prove_code_safety(): extraccion de constraints desde AST real
- Timeout configurable (15s quirurgico)
- gc.collect() tras operaciones pesadas

Cuando Z3 NO esta disponible (Android/Termux):
- Fallback automatico a ConstraintSolver (AC-3 + Backtracking)
- Mismo contrato de interfaz, poder expresivo reducido
"""

from .z3_parts import Z3Solver, HAS_Z3

__all__ = ["Z3Solver", "HAS_Z3"]
