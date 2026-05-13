"""
ZENIC-AGENTS - Symbolic Types

Data types for the Bounded Symbolic Execution engine:
- SymbolicValue: Represents a symbolic value with associated constraint
- SymbolicPath: Represents an execution path with path conditions (string + Z3)
"""

import logging

logger = logging.getLogger(__name__)

from ..z3_solver import HAS_Z3

# Z3 module reference for convenience (only available when HAS_Z3 is True)
if HAS_Z3:
    import z3 as z3_module


class SymbolicValue:
    """Representa un valor simbolico con constraint asociada."""

    def __init__(self, name, var_type="any", constraint=None, concrete=None):
        self.name = name
        self.var_type = var_type
        self.constraint = constraint  # Funcion lambda que debe cumplir
        self.concrete = concrete  # Valor concreto conocido (int, str, None, etc.)

    def __repr__(self):
        if self.concrete is not None:
            return f"Sym({self.name}:{self.var_type}={self.concrete!r})"
        return f"Sym({self.name}:{self.var_type})"


class SymbolicPath:
    """
    Representa un camino de ejecucion simbolica con path condition.

    Mantiene condiciones tanto en formato string (para AC-3 fallback)
    como en formato Z3 (para verificacion formal cuando Z3 esta disponible).
    """

    MAX_Z3_CONDITIONS = 50  # Limite de condiciones Z3 por camino (memoria-safe)

    def __init__(self, condition=None, result=None, is_pruned=False, variables=None,
                 z3_conditions=None, assignments=None, return_values=None):
        self.condition = condition or []  # Lista de condiciones simbolicas (string)
        self.result = result  # Resultado al final del camino
        self.is_pruned = is_pruned  # Si fue podado por I/O
        self.variables = variables if variables is not None else {}  # Estado de variables simbolicas
        self.z3_conditions = z3_conditions if z3_conditions is not None else []  # Z3 constraints
        self.assignments = assignments if assignments is not None else []  # Historial de asignaciones
        self.return_values = return_values if return_values is not None else []  # Valores de return

    def add_condition(self, cond, z3_cond=None):
        """Agrega una condicion al path condition (string y opcionalmente Z3)."""
        self.condition.append(cond)
        if z3_cond is not None and len(self.z3_conditions) < self.MAX_Z3_CONDITIONS:
            self.z3_conditions.append(z3_cond)

    def add_assignment(self, var_name, value_desc):
        """Registra una asignacion de variable en este camino."""
        self.assignments.append((var_name, value_desc))

    def add_return(self, return_desc, return_type="any"):
        """Registra un valor de retorno en este camino."""
        self.return_values.append({"desc": return_desc, "type": return_type})

    def is_feasible(self):
        """
        Verifica si el path condition es satisfacible.

        Usa Z3 cuando esta disponible para verificacion formal real.
        Fallback a verificacion string-based cuando Z3 no esta instalado.
        """
        if not self.condition and not self.z3_conditions:
            return True

        if HAS_Z3 and self.z3_conditions:
            return self._is_feasible_z3()
        return self._is_feasible_string()

    def _is_feasible_z3(self):
        """Verificacion de factibilidad usando Z3 SMT Solver."""
        try:
            solver = z3_module.Solver()
            solver.set("timeout", 500)  # 500ms para feasibility check
            for cond in self.z3_conditions:
                solver.add(cond)
            result = solver.check()
            return result != z3_module.unsat
        except Exception as e:
            # Fallback a string-based si Z3 falla
            logger.debug("SymbolicPath: Z3 feasibility check failed: %s", e)
            return self._is_feasible_string()

    def _is_feasible_string(self):
        """Verificacion de factibilidad basada en strings (AC-3 fallback)."""
        if not self.condition:
            return True
        # Verificar contradicciones obvias
        negations = set()
        affirmations = set()
        for cond in self.condition:
            cond_str = str(cond)
            if cond_str.startswith("NOT_"):
                negations.add(cond_str[4:])
            else:
                affirmations.add(cond_str)
        # Si afirmamos y negamos lo mismo, es infeasible
        return not (affirmations & negations)
