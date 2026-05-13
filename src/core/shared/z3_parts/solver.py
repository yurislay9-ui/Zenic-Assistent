"""
Z3Solver Public API Class.

Combines all mixin classes into the final Z3Solver class with:
- Constructor and configuration
- Public API methods that delegate to Z3 or AC-3 fallback implementations
- prove_code_safety: Comprehensive code safety verification orchestrator
"""

import gc
import logging
from typing import Any, Callable, Dict, List, Set

try:
    import z3 as z3_module
    HAS_Z3 = True
except ImportError:
    HAS_Z3 = False

from .null_safety import Z3NullSafetyMixin
from .type_safety import Z3TypeSafetyMixin
from .type_lattice import Z3TypeLatticeMixin
from .invariants import Z3InvariantMixin
from .invariants_patterns import Z3InvariantPatternsMixin
from .solver_core import Z3SolverCoreMixin
from .solver_encoding import Z3SolverEncodingMixin
from .ac3_fallback import AC3FallbackMixin

from ..constraint_solver import Constraint, ConstraintSolver

logger = logging.getLogger(__name__)


class Z3Solver(
    Z3NullSafetyMixin,
    Z3TypeLatticeMixin,
    Z3TypeSafetyMixin,
    Z3InvariantMixin,
    Z3InvariantPatternsMixin,
    Z3SolverEncodingMixin,
    Z3SolverCoreMixin,
    AC3FallbackMixin,
):
    """
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

    def __init__(self, timeout_ms: int = 15000):
        self.timeout_ms = timeout_ms
        self._solver_type = "Z3" if HAS_Z3 else "AC3_FALLBACK"
        # Bidirectional mapping for bijective value encoding
        self._encode_map = {}   # value -> int
        self._decode_map = {}   # int -> value
        self._next_encode_id = 0
        # Monotonic counter for unique Z3 sort names (avoids 'already declared' errors)
        self._sort_counter = 0

    @property
    def solver_type(self) -> str:
        return self._solver_type

    # ================================================================
    #  Public API - same signatures as before + new prove_code_safety
    # ================================================================

    def prove_null_safety(self, variable_names: List[str], nullable_vars: Set[str]) -> Dict[str, Any]:
        """
        Verifica que variables no-nullable nunca reciben valor None.

        Args:
            variable_names: list de nombres de todas las variables
            nullable_vars: set de nombres de variables que PUEDEN ser None

        Returns:
            dict con status, solver_type, y counterexamples si los hay
        """
        if HAS_Z3:
            self._reset_z3_state()  # Phase 3: prevent memory leak
            return self._z3_prove_null_safety(variable_names, nullable_vars)
        return self._ac3_prove_null_safety(variable_names, nullable_vars)

    def prove_type_safety(self, variables_with_types: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Verifica consistencia de tipos en operaciones.

        Args:
            variables_with_types: list de {"name": str, "types": [str]}

        Returns:
            dict con status y resultados
        """
        if HAS_Z3:
            self._reset_z3_state()  # Phase 3: prevent memory leak
            return self._z3_prove_type_safety(variables_with_types)
        return self._ac3_prove_type_safety(variables_with_types)

    def prove_invariant(self, invariant_func: Callable[..., bool], variables: List[str], domains: Dict[str, List[Any]]) -> Dict[str, Any]:
        """
        Verifica una invariante sobre dominios de variables.

        Args:
            invariant_func: funcion(**kwargs) -> bool
            variables: list de nombres de variables
            domains: dict {variable: [valores_posibles]}

        Returns:
            dict con status: PROVEN, VIOLATED, TIMEOUT
        """
        if HAS_Z3:
            self._reset_z3_state()  # Phase 3: prevent memory leak
            return self._z3_prove_invariant(invariant_func, variables, domains)
        # Fallback: usar AC-3 solver para verificacion exhaustiva
        solver = ConstraintSolver(timeout_ms=self.timeout_ms)
        return solver.verify_invariant(invariant_func, variables, domains)

    def solve_constraints(self, domains: Dict[str, List[Any]], constraints: List[Constraint]) -> Dict[str, Any]:
        """
        Resuelve un sistema de restricciones.

        Args:
            domains: dict {variable: [valores_posibles]}
            constraints: list of Constraint objects

        Returns:
            dict con status y assignment
        """
        if HAS_Z3:
            return self._z3_solve(domains, constraints)
        # Fallback: AC-3 + Backtracking
        solver = ConstraintSolver(timeout_ms=self.timeout_ms)
        return solver.solve(domains, constraints)

    def prove_code_safety(self, ast_analysis: Dict[str, Any], raw_code: str) -> Dict[str, Any]:
        """
        MAIN new method: Extracts REAL constraints from code via AST analysis
        and proves safety properties using Z3 with deep semantic encoding.

        Args:
            ast_analysis: dict from AST analysis with keys like:
                - 'variables': list of {'name': str, 'annotation': str|None, 'nullable': bool}
                - 'functions': list of {'name': str, 'return_type': str|None, 'params': [...]}
                - 'operations': list of {'op': str, 'left_type': str, 'right_type': str}
                - 'invariants': list of {'kind': str, 'expr': str, 'variables': [...]}
            raw_code: str of the source code being verified

        Returns:
            dict with comprehensive proof results including:
                - null_safety: result of null-safety proof
                - type_safety: result of type-safety proof
                - invariant_safety: result of invariant verification
                - overall_status: PROVEN | VIOLATED | PARTIAL | ERROR
                - model: Z3 model (if available)
        """
        if not HAS_Z3:
            return self._ac3_prove_code_safety(ast_analysis, raw_code)

        results = {
            "null_safety": None,
            "type_safety": None,
            "invariant_safety": None,
            "overall_status": "UNKNOWN",
            "solver_type": "Z3_DEEP",
            "model": None,
            "errors": [],
        }

        try:
            # Reset Z3 state for this proof session (Phase 3: prevent memory leak)
            self._reset_z3_state()

            # ---- Phase 1: Extract variable nullability from annotations ----
            variables_info = ast_analysis.get("variables", [])
            all_var_names = [v["name"] for v in variables_info]
            nullable_vars = set()
            for v in variables_info:
                annotation = v.get("annotation") or ""
                if v.get("nullable", False):
                    nullable_vars.add(v["name"])
                elif isinstance(annotation, str) and (
                    "Optional" in annotation
                    or "None" in annotation
                    or annotation == "None"
                ):
                    nullable_vars.add(v["name"])

            # ---- Phase 2: Null-safety proof with EnumSort ----
            if all_var_names:
                results["null_safety"] = self._z3_prove_null_safety(
                    all_var_names, nullable_vars
                )

            # ---- Phase 3: Type-safety proof with EnumSort + compatibility ----
            functions_info = ast_analysis.get("functions", [])
            operations_info = ast_analysis.get("operations", [])

            # Build variables_with_types from annotations
            variables_with_types = []
            for v in variables_info:
                annotation = v.get("annotation") or "unknown"
                # Flatten Optional[X] -> include both X and None
                types_for_var = self._annotation_to_types(annotation)
                if v.get("nullable", False) or (
                    isinstance(annotation, str) and "Optional" in annotation
                ):
                    if "None" not in types_for_var:
                        types_for_var.append("None")
                variables_with_types.append({
                    "name": v["name"],
                    "types": types_for_var if types_for_var else ["unknown"],
                })

            # Add function return types as variables
            for func in functions_info:
                ret_type = func.get("return_type") or "unknown"
                types_for_ret = self._annotation_to_types(ret_type)
                variables_with_types.append({
                    "name": f"__return_{func['name']}",
                    "types": types_for_ret if types_for_ret else ["unknown"],
                })

            if variables_with_types:
                # Pass operations for real compatibility checking
                results["type_safety"] = self._z3_prove_type_safety_deep(
                    variables_with_types, operations_info
                )

            # ---- Phase 4: Invariant verification from code patterns ----
            invariants_info = ast_analysis.get("invariants", [])
            if invariants_info:
                results["invariant_safety"] = self._z3_prove_code_invariants(
                    invariants_info, variables_info
                )
            else:
                # Try to extract invariants from raw_code patterns
                results["invariant_safety"] = self._z3_prove_pattern_invariants(
                    raw_code, variables_info
                )

            # ---- Phase 5: Compute overall status ----
            sub_results = [
                results["null_safety"],
                results["type_safety"],
                results["invariant_safety"],
            ]
            sub_results = [r for r in sub_results if r is not None]

            if not sub_results:
                results["overall_status"] = "UNKNOWN"
            elif all(r.get("verified", False) for r in sub_results):
                results["overall_status"] = "PROVEN"
            elif any(
                r.get("status") in ("VIOLATED", "UNSATISFIABLE") for r in sub_results
            ):
                results["overall_status"] = "VIOLATED"
            else:
                results["overall_status"] = "PARTIAL"

            # Try to extract a model from any sat result
            for r in sub_results:
                model = r.get("model")
                if model is not None:
                    results["model"] = model
                    break

        except Exception as e:
            logger.error("Z3 deep code-safety proof error: %s", e)
            results["errors"].append(str(e))
            results["overall_status"] = "ERROR"

        # Free memory
        gc.collect()

        return results
