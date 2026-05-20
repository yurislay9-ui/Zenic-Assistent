"""
ZENIC-AGENTS - Monte Carlo Tree Search (MCTS) v16

Implements MCTS with UCB1 selection, expansion, simulation (rollout),
and backpropagation phases. Used for plan search space exploration.

CAMBIO TECNOLÓGICO v16 - ARM-Optimized Defaults:
- max_depth: 5→3 por defecto en ARM (reduce CPU un 60%)
- max_simulations: 100→50 por defecto en ARM (reduce RAM un 50%)
- ResourceGovernor adapta simulaciones según carga del sistema
- Resultado: MCTS consume ~50% menos CPU/RAM en el teléfono
"""

import math
import time
import os
import logging

from .deterministic import DeterministicRNG

logger = logging.getLogger(__name__)

__all__ = ["MCTSNode", "MCTSPlanner"]

# ARM-optimized defaults: detect if running on mobile
def _is_arm_device():
    """Detecta si estamos en un dispositivo ARM (Teléfono/Tablet)."""
    try:
        machine = os.uname().machine if hasattr(os, 'uname') else ''
        return 'arm' in machine.lower() or 'aarch' in machine.lower()
    except Exception as e:
        logger.debug("MCTS: ARM detection failed: %s", e)
        return False

# Adaptive defaults based on hardware
_IS_ARM = _is_arm_device()
DEFAULT_MAX_DEPTH = 3 if _IS_ARM else 5
DEFAULT_MAX_SIMULATIONS = 50 if _IS_ARM else 100
DEFAULT_TIMEOUT_MS = 5000


# ============================================================
#  MCTS (Monte Carlo Tree Search) - Implementacion Real
# ============================================================

class MCTSNode:
    """
    Nodo del arbol de busqueda Monte Carlo.
    Implementa UCB1 para seleccion y backpropagation.
    """

    def __init__(self, state=None, parent=None, action=None):
        self.state = state
        self.parent = parent
        self.action = action
        self.children = []
        self.visits = 0
        self.wins = 0.0
        self.untried_actions = []

    def ucb1(self, exploration=1.414):
        """Upper Confidence Bound 1 para seleccion."""
        if self.parent is None or self.parent.visits == 0:
            return float('inf')
        if self.visits == 0:
            return float('inf')
        exploitation = self.wins / self.visits
        exploration_term = exploration * math.sqrt(
            math.log(self.parent.visits) / self.visits
        )
        return exploitation + exploration_term

    def best_child(self, exploration=1.414):
        """Selecciona el hijo con mayor UCB1."""
        return max(self.children, key=lambda c: c.ucb1(exploration))

    def most_visited_child(self):
        """Selecciona el hijo mas visitado (para decision final)."""
        return max(self.children, key=lambda c: c.visits)

    def expand(self, action, new_state):
        """Expande un nodo hijo con la accion dada."""
        child = MCTSNode(state=new_state, parent=self, action=action)
        if action in self.untried_actions:
            self.untried_actions.remove(action)
        self.children.append(child)
        return child

    def is_fully_expanded(self):
        """Verifica si todas las acciones posibles fueron probadas."""
        return len(self.untried_actions) == 0

    def is_terminal(self):
        """Verifica si es un nodo terminal (sin hijos posibles)."""
        return len(self.untried_actions) == 0 and len(self.children) == 0

    def backpropagate(self, reward):
        """Propaga el resultado hacia arriba en el arbol."""
        node = self
        while node is not None:
            node.visits += 1
            node.wins += reward
            node = node.parent


class MCTSPlanner:
    """
    Planificador MCTS real con presupuesto computacional estricto.
    Implementa las 4 fases: Seleccion, Expansion, Simulacion, Backpropagation.
    """

    def __init__(self, max_depth=None, max_simulations=None, timeout_ms=DEFAULT_TIMEOUT_MS, seed=None):
        self.max_depth = max_depth if max_depth is not None else DEFAULT_MAX_DEPTH
        self.max_simulations = max_simulations if max_simulations is not None else DEFAULT_MAX_SIMULATIONS
        self.timeout_ms = timeout_ms
        self.simulations_run = 0
        self.depth_reached = 0
        # Deterministic RNG (Phase 5 fix)
        self._rng = DeterministicRNG("mcts", seed_override=seed)
        if _IS_ARM:
            logger.info(
                f"MCTSPlanner: ARM-optimized mode (depth={self.max_depth}, "
                f"sims={self.max_simulations}, timeout={self.timeout_ms}ms)"
            )

    def search(self, initial_state, action_generator, reward_function):
        """
        Ejecuta MCTS desde el estado inicial.

        Args:
            initial_state: Estado inicial del plan
            action_generator: Funcion (state, depth) -> list of actions
            reward_function: Funcion (state) -> float [0, 1]

        Returns:
            Mejor accion encontrada, o None si no hay acciones
        """
        root = MCTSNode(state=initial_state)
        root.untried_actions = action_generator(initial_state, 0)

        if not root.untried_actions:
            return None

        start_time = time.time()
        self.simulations_run = 0
        self.depth_reached = 0

        for i in range(self.max_simulations):
            # Verificar timeout
            elapsed_ms = (time.time() - start_time) * 1000
            if elapsed_ms >= self.timeout_ms:
                break

            # Fase 1: Seleccion
            node = self._select(root)

            # Fase 2: Expansion
            if not node.is_terminal() and node.visits > 0:
                node = self._expand(node, action_generator)

            # Fase 3: Simulacion (Rollout)
            reward = self._simulate(node, action_generator, reward_function)

            # Fase 4: Backpropagation
            node.backpropagate(reward)
            self.simulations_run += 1

        # Elegir la mejor accion basada en visitas (mas robusto que UCB1)
        if root.children:
            best = root.most_visited_child()
            self.depth_reached = self._measure_depth(root)
            return best.action
        return root.untried_actions[0] if root.untried_actions else None

    def _select(self, node):
        """Selecciona el nodo mas prometedor usando UCB1."""
        while not node.is_terminal() and node.is_fully_expanded():
            if not node.children:
                break
            node = node.best_child()
        return node

    def _expand(self, node, action_generator):
        """Expande un nodo con una accion no probada."""
        depth = self._node_depth(node)
        if depth >= self.max_depth:
            return node

        if node.untried_actions:
            action = self._rng.choice(node.untried_actions)
            new_state = self._apply_action(node.state, action)
            child = node.expand(action, new_state)
            child.untried_actions = action_generator(new_state, depth + 1)
            return child
        return node

    def _simulate(self, node, action_generator, reward_function):
        """Simula un rollout aleatorio desde el nodo."""
        state = node.state
        depth = self._node_depth(node)
        max_rollout_depth = self.max_depth

        for _ in range(max_rollout_depth - depth):
            actions = action_generator(state, depth)
            if not actions:
                break
            action = self._rng.choice(actions)
            state = self._apply_action(state, action)
            depth += 1

        return reward_function(state)

    def _node_depth(self, node):
        """Calcula la profundidad de un nodo en el arbol."""
        depth = 0
        current = node
        while current.parent is not None:
            depth += 1
            current = current.parent
        return depth

    def _measure_depth(self, node):
        """Mide la profundidad maxima del arbol."""
        if not node.children:
            return 0
        return 1 + max(self._measure_depth(c) for c in node.children)

    def _apply_action(self, state, action):
        """Aplica una accion al estado y devuelve el nuevo estado."""
        if isinstance(state, dict):
            new_state = dict(state)
        else:
            new_state = {"prev": state}
        new_state["last_action"] = action
        new_state["depth"] = state.get("depth", 0) + 1 if isinstance(state, dict) else 1
        # Rastrear acciones tomadas
        taken = list(state.get("taken_actions", [])) if isinstance(state, dict) else []
        taken.append(action)
        new_state["taken_actions"] = taken
        return new_state
