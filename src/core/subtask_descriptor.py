"""
SubtaskDescriptor - Enriched subtask descriptor for the Abortive Protocol.

A diferencia de las subtareas como strings de texto plano, este
descriptor preserva todo el contexto del pipeline que generó la
subtarea, permitiendo que cada subtarea se ejecute con conocimiento
del análisis previo en vez de empezar desde cero.
"""

from typing import Any, Dict, List, Optional


class SubtaskDescriptor:
    """
    Descriptor de subtarea enriquecido para el Protocolo Abortivo.

    A diferencia de las subtareas como strings de texto plano, este
    descriptor preserva todo el contexto del pipeline que generó la
    subtarea, permitiendo que cada subtarea se ejecute con conocimiento
    del análisis previo en vez de empezar desde cero.

    Attributes:
        message: Mensaje de texto para el parser (compatible con pipeline)
        target: Nodo objetivo específico de la subtarea
        operation: Tipo de operación (CREATE, REFACTOR, DEBUG, etc.)
        goal: Objetivo de la subtarea
        solver_insights: Resultados del solver Z3/AC-3 del análisis padre
        mcts_hints: Acción sugerida por MCTS del plan padre
        parent_violations: Violaciones simbólicas detectadas en el padre
        parent_context: Análisis AST y métricas del nivel padre
        depth: Profundidad de recursión en subdivisión
    """

    def __init__(self, message: str, target: str = "", operation: str = "", goal: str = "",
                 solver_insights: Optional[Dict[str, Any]] = None, mcts_hints: Optional[List[Any]] = None,
                 parent_violations: Optional[List[Any]] = None,
                 parent_context: Optional[Dict[str, Any]] = None, depth: int = 0):
        self.message = message
        self.target = target
        self.operation = operation
        self.goal = goal
        self.solver_insights = solver_insights or {}
        self.mcts_hints = mcts_hints or []
        self.parent_violations = parent_violations or []
        self.parent_context = parent_context or {}
        self.depth = depth

    def __repr__(self):
        """Return a concise representation showing key attributes."""
        return (
            f"SubtaskDescriptor("
            f"message={self.message!r}, "
            f"target={self.target!r}, "
            f"operation={self.operation!r}, "
            f"goal={self.goal!r}, "
            f"depth={self.depth})"
        )

    def to_message(self):
        """Convierte el descriptor a mensaje de texto para el parser."""
        return self.message

    def to_dict(self):
        """Serializa el descriptor para logging y respuesta."""
        return {
            "message": self.message,
            "target": self.target,
            "operation": self.operation,
            "goal": self.goal,
            "solver_insights": self.solver_insights,
            "mcts_hints": self.mcts_hints,
            "parent_violations_count": len(self.parent_violations),
            "depth": self.depth,
        }
