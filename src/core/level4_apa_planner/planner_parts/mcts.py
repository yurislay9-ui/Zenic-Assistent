"""Mixin: MCTS action generator and reward function for APAPlanner."""

from ._imports import OperationType

# MCTS reward weight constants
_MCTS_BASE_REWARD = 0.1
_MCTS_DEPTH_REWARD = 0.1
_MCTS_VALIDATION_REWARD = 0.2
_MCTS_COMPLETENESS_BONUS = 0.3
_MCTS_SHALLOW_PENALTY = 0.1


class MCTSMixin:
    """Mixin providing MCTS action generation and reward function."""

    def _action_generator(self, state, depth):
        """Genera acciones posibles desde un estado del plan."""
        if depth >= self.MCTS_MAX_DEPTH:
            return []

        op = state.get("op", "")
        actions = []

        if op == OperationType.CREATE:
            actions = ["ANALYZE_STRUCTURE", "SCRAPE_PATTERNS", "GENERATE_CODE",
                       "VALIDATE_SECURITY", "SYMBOLIC_VALIDATION"]
        elif op == OperationType.REFACTOR:
            actions = ["ANALYZE_PATTERNS", "REPLACE_AST_NODE", "VALIDATE_INTERFACE",
                       "SYMBOLIC_VALIDATION", "RUN_TESTS"]
        elif op == OperationType.DEBUG:
            actions = ["TRACE_EXECUTION", "PATCH_FIX", "VALIDATE_FIX",
                       "SYMBOLIC_VALIDATION"]
        elif op == OperationType.DELETE:
            actions = ["CHECK_DEPENDENCIES", "DELETE_AST_NODE", "VALIDATE_NO_BREAKAGE"]
        elif op == OperationType.OPTIMIZE:
            actions = ["ANALYZE_PATTERNS", "REPLACE_AST_NODE", "BENCHMARK",
                       "VALIDATE_PERFORMANCE"]
        elif op == OperationType.ANALYZE:
            actions = ["ANALYZE_STRUCTURE", "QUALITY_REPORT", "SUGGEST_IMPROVEMENTS"]
        elif op == OperationType.EXPLAIN:
            actions = ["EXPLAIN_CODE", "GENERATE_DOCS"]
        elif op == OperationType.SEARCH:
            actions = ["SEARCH_DEFINITION", "FIND_REFERENCES"]
        else:
            actions = ["QUICK_ANALYSIS"]

        # Filtrar acciones ya tomadas en este camino
        taken = state.get("taken_actions", [])
        available = [a for a in actions if a not in taken]

        return available

    def _reward_function(self, state):
        """
        Funcion de recompensa para MCTS.
        Premia planes que: cubren mas operaciones, son mas profundos,
        incluyen validacion, y terminan en estados completos.
        """
        reward = _MCTS_BASE_REWARD
        depth = state.get("depth", 0)
        taken = state.get("taken_actions", [])

        # Premiar profundidad (hasta el limite)
        reward += min(depth, self.MCTS_MAX_DEPTH) * _MCTS_DEPTH_REWARD

        # Premiar inclusion de validacion
        validation_actions = [a for a in taken if "VALIDATE" in a or "SYMBOLIC" in a]
        reward += len(validation_actions) * _MCTS_VALIDATION_REWARD

        # Premiar planes completos (que incluyen generacion + validacion)
        has_generation = any(a in taken for a in ["GENERATE_CODE", "REPLACE_AST_NODE", "PATCH_FIX"])
        has_validation = len(validation_actions) > 0
        if has_generation and has_validation:
            reward += _MCTS_COMPLETENESS_BONUS

        # Penalizar planes muy superficiales
        if depth < 2 and len(taken) < 2:
            reward -= _MCTS_SHALLOW_PENALTY

        return max(0.0, min(1.0, reward))
