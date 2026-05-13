"""
ZENIC-AGENTS - Constraint Solver (AC-3 + Backtracking) v16

Implements a Constraint Satisfaction Problem solver using:
- AC-3 algorithm for arc consistency
- Backtracking search with MRV heuristic
- Timeout enforcement

Fallback when Z3 is not available.
"""

import time
import random
import logging
from collections import deque
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

__all__ = ["Constraint", "ConstraintSolver"]


# ============================================================
#  CONSTRAINT SOLVER (AC-3 + Backtracking) - Fallback sin Z3
# ============================================================

class Constraint:
    """Representa una restriccion entre variables."""

    def __init__(self, var1: str, var2: str, predicate: Callable[[Any, Any], bool], description: str = ""):
        self.var1 = var1
        self.var2 = var2
        self.predicate = predicate
        self.description = description

    def satisfied(self, val1, val2):
        return self.predicate(val1, val2)


class ConstraintSolver:
    """
    Solver de restricciones usando AC-3 (Arc Consistency)
    y Backtracking Search con timeout.
    Fallback cuando Z3 no esta disponible.
    """

    def __init__(self, timeout_ms: int = 5000):
        self.timeout_ms = timeout_ms
        self._start_time = 0
        self._timed_out = False

    def solve(self, domains: Dict[str, List[Any]], constraints: List[Constraint]) -> Dict[str, Any]:
        """Resuelve un CSP (Constraint Satisfaction Problem)."""
        self._start_time = time.time()
        self._timed_out = False

        domains = {v: list(d) for v, d in domains.items()}

        # Fase 1: AC-3 para reducir dominios
        if not self._ac3(domains, constraints):
            return {"status": "UNSATISFIABLE", "assignment": None}

        if self._check_timeout():
            return {"status": "TIMEOUT", "assignment": None}

        # Fase 2: Backtracking search
        assignment = {}
        result = self._backtrack(assignment, domains, constraints)

        if self._timed_out:
            return {"status": "TIMEOUT", "assignment": None}

        if result is not None:
            return {"status": "SATISFIED", "assignment": result}
        return {"status": "UNSATISFIABLE", "assignment": None}

    def verify_invariant(self, condition_func: Callable[..., bool], variables: List[str], domains: Dict[str, List[Any]]) -> Dict[str, Any]:
        """Verifica si una invariante se cumple en todos los estados posibles."""
        self._start_time = time.time()
        self._timed_out = False

        total_combinations = 1
        for v in variables:
            if v in domains:
                total_combinations *= len(domains[v])

        if total_combinations > 10000:
            return self._sample_verify(condition_func, variables, domains, 1000)

        counterexamples = []
        checked = 0

        def enumerate_all(var_idx, current_assignment):
            nonlocal checked
            if self._check_timeout():
                return

            if var_idx >= len(variables):
                checked += 1
                try:
                    if not condition_func(**current_assignment):
                        counterexamples.append(dict(current_assignment))
                except Exception as e:
                    logger.debug(f"ConstraintSolver: Invariant condition evaluation failed: {e}")
                return

            var = variables[var_idx]
            if var not in domains:
                enumerate_all(var_idx + 1, current_assignment)
                return

            for val in domains[var]:
                current_assignment[var] = val
                enumerate_all(var_idx + 1, current_assignment)
                if self._timed_out or len(counterexamples) >= 3:
                    return

            if var in current_assignment:
                del current_assignment[var]

        enumerate_all(0, {})

        if self._timed_out:
            return {
                "status": "TIMEOUT",
                "verified": False,
                "counterexamples": counterexamples,
                "checked": checked
            }

        if counterexamples:
            return {
                "status": "VIOLATED",
                "verified": False,
                "counterexamples": counterexamples,
                "checked": checked
            }

        return {
            "status": "PROVEN",
            "verified": True,
            "counterexamples": [],
            "checked": checked
        }

    def _sample_verify(self, condition_func, variables, domains, samples):
        """Verificacion por muestreo cuando hay demasiadas combinaciones."""
        violations = []

        for _ in range(samples):
            if self._check_timeout():
                break

            assignment = {}
            for var in variables:
                if var in domains and domains[var]:
                    assignment[var] = random.choice(domains[var])

            try:
                if not condition_func(**assignment):
                    violations.append(assignment)
                    if len(violations) >= 3:
                        break
            except Exception as e:
                logger.debug(f"ConstraintSolver: Sample verify condition evaluation failed: {e}")

        if self._timed_out:
            return {"status": "TIMEOUT", "verified": False, "counterexamples": violations}
        if violations:
            return {"status": "LIKELY_VIOLATED", "verified": False, "counterexamples": violations}
        return {"status": "LIKELY_PROVEN", "verified": True, "counterexamples": [], "checked": samples}

    def _ac3(self, domains, constraints):
        """Algoritmo AC-3 para consistencia de arcos.

        FIX (Phase 5): Replaced list.pop(0) with deque.popleft() for O(1)
        dequeue instead of O(n). AC-3 processes many arcs, so this
        significantly reduces CPU overhead on large constraint systems.
        """
        queue = deque()
        for c in constraints:
            queue.append((c.var1, c.var2, c))
            queue.append((c.var2, c.var1, c))

        while queue:
            if self._check_timeout():
                return True

            xi, xj, constraint = queue.popleft()
            if self._revise(domains, xi, xj, constraint):
                if not domains[xi]:
                    return False
                for c in constraints:
                    if c.var1 != xj and c.var2 == xi:
                        queue.append((c.var1, xi, c))
                    elif c.var2 != xj and c.var1 == xi:
                        queue.append((c.var2, xi, c))
        return True

    def _revise(self, domains, xi, xj, constraint):
        """Elimina valores inconsistentes del dominio de xi."""
        revised = False
        for x in list(domains[xi]):
            has_support = False
            for y in domains[xj]:
                if constraint.var1 == xi:
                    if constraint.satisfied(x, y):
                        has_support = True
                        break
                else:
                    if constraint.satisfied(y, x):
                        has_support = True
                        break

            if not has_support:
                domains[xi].remove(x)
                revised = True
        return revised

    def _backtrack(self, assignment, domains, constraints):
        """Busqueda con backtracking."""
        if self._check_timeout():
            self._timed_out = True
            return None

        if len(assignment) == len(domains):
            return dict(assignment)

        var = min(
            (v for v in domains if v not in assignment),
            key=lambda v: len(domains[v])
        )

        for val in domains[var]:
            assignment[var] = val

            if self._is_consistent(var, val, assignment, constraints):
                result = self._backtrack(assignment, domains, constraints)
                if result is not None:
                    return result

            del assignment[var]

        return None

    def _is_consistent(self, var, val, assignment, constraints):
        """Verifica si la asignacion es consistente con las restricciones."""
        for c in constraints:
            if c.var1 == var and c.var2 in assignment:
                if not c.satisfied(val, assignment[c.var2]):
                    return False
            elif c.var2 == var and c.var1 in assignment:
                if not c.satisfied(assignment[c.var1], val):
                    return False
        return True

    def _check_timeout(self):
        """Verifica si se excedio el timeout."""
        elapsed = (time.time() - self._start_time) * 1000
        if elapsed >= self.timeout_ms:
            self._timed_out = True
            return True
        return False
