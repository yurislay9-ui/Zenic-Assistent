"""
Unit tests for MCTS (Monte Carlo Tree Search)

Tests UCB1 selection, expansion, simulation, backpropagation,
and the MCTSPlanner budget enforcement.
"""

import pytest
from src.core.shared.mcts import MCTSNode, MCTSPlanner


class TestMCTSNode:
    """Tests for MCTSNode."""

    def test_ucb1_unvisited_returns_inf(self):
        """Unvisited nodes should return infinity for UCB1."""
        node = MCTSNode(state={})
        assert node.ucb1() == float('inf')

    def test_ucb1_visited_returns_finite(self):
        """Visited nodes should return finite UCB1 values."""
        parent = MCTSNode(state={})
        parent.visits = 10
        child = MCTSNode(state={}, parent=parent)
        child.visits = 5
        child.wins = 3.0
        ucb = child.ucb1()
        assert ucb != float('inf')
        assert ucb > 0

    def test_best_child_selects_highest_ucb1(self):
        """best_child should select the child with highest UCB1."""
        parent = MCTSNode(state={})
        parent.visits = 20

        child1 = MCTSNode(state={}, parent=parent)
        child1.visits = 10
        child1.wins = 8.0

        child2 = MCTSNode(state={}, parent=parent)
        child2.visits = 10
        child2.wins = 2.0

        parent.children = [child1, child2]
        best = parent.best_child()
        assert best is child1

    def test_expand_creates_child(self):
        """expand should create a new child node."""
        parent = MCTSNode(state={})
        parent.untried_actions = ["A", "B"]
        child = parent.expand("A", {"action": "A"})
        assert child.action == "A"
        assert child in parent.children
        assert "A" not in parent.untried_actions

    def test_is_fully_expanded(self):
        """is_fully_expanded should be True when no untried actions remain."""
        node = MCTSNode(state={})
        node.untried_actions = ["A"]
        assert not node.is_fully_expanded()
        node.untried_actions = []
        assert node.is_fully_expanded()

    def test_is_terminal(self):
        """is_terminal should be True when no actions and no children."""
        node = MCTSNode(state={})
        node.untried_actions = []
        assert node.is_terminal()
        node.untried_actions = ["A"]
        assert not node.is_terminal()

    def test_backpropagate_updates_ancestors(self):
        """backpropagate should update visits and wins up to root."""
        root = MCTSNode(state={})
        child = MCTSNode(state={}, parent=root)
        grandchild = MCTSNode(state={}, parent=child)

        grandchild.backpropagate(1.0)

        assert grandchild.visits == 1
        assert grandchild.wins == 1.0
        assert child.visits == 1
        assert child.wins == 1.0
        assert root.visits == 1
        assert root.wins == 1.0

    def test_most_visited_child(self):
        """most_visited_child should return the child with most visits."""
        parent = MCTSNode(state={})
        c1 = MCTSNode(state={}, parent=parent)
        c1.visits = 5
        c2 = MCTSNode(state={}, parent=parent)
        c2.visits = 15
        c3 = MCTSNode(state={}, parent=parent)
        c3.visits = 10
        parent.children = [c1, c2, c3]
        assert parent.most_visited_child() is c2


class TestMCTSPlanner:
    """Tests for MCTSPlanner."""

    @pytest.fixture
    def simple_action_generator(self):
        """Simple action generator for testing."""
        def _gen(state, depth):
            if depth >= 3:
                return []
            return ["ACTION_A", "ACTION_B"]
        return _gen

    @pytest.fixture
    def simple_reward_function(self):
        """Simple reward that prefers deeper states."""
        def _reward(state):
            return min(state.get("depth", 0) / 3.0, 1.0)
        return _reward

    def test_search_returns_action(self, simple_action_generator, simple_reward_function):
        """MCTS search should return an action."""
        planner = MCTSPlanner(max_depth=3, max_simulations=20, timeout_ms=5000)
        initial_state = {"target": "test", "op": "CREATE", "goal": "add", "depth": 0, "taken_actions": []}
        result = planner.search(initial_state, simple_action_generator, simple_reward_function)
        assert result is not None
        assert result in ["ACTION_A", "ACTION_B"]

    def test_search_respects_timeout(self, simple_action_generator, simple_reward_function):
        """MCTS should respect the timeout budget."""
        planner = MCTSPlanner(max_depth=10, max_simulations=100000, timeout_ms=100)
        initial_state = {"target": "test", "op": "CREATE", "goal": "add", "depth": 0, "taken_actions": []}
        result = planner.search(initial_state, simple_action_generator, simple_reward_function)
        # Should complete within reasonable time, not 100k sims
        assert planner.simulations_run < 100000

    def test_search_no_actions_returns_none(self, simple_reward_function):
        """MCTS should return None when no actions are available."""
        planner = MCTSPlanner(max_depth=3, max_simulations=10, timeout_ms=1000)
        no_actions = lambda state, depth: []
        initial_state = {"depth": 0}
        result = planner.search(initial_state, no_actions, simple_reward_function)
        assert result is None

    def test_search_tracks_simulations_run(self, simple_action_generator, simple_reward_function):
        """MCTS should track how many simulations were run."""
        planner = MCTSPlanner(max_depth=3, max_simulations=10, timeout_ms=5000)
        initial_state = {"target": "test", "op": "CREATE", "goal": "add", "depth": 0, "taken_actions": []}
        planner.search(initial_state, simple_action_generator, simple_reward_function)
        assert planner.simulations_run > 0
        assert planner.simulations_run <= 10

    def test_search_tracks_depth_reached(self, simple_action_generator, simple_reward_function):
        """MCTS should track the maximum depth reached."""
        planner = MCTSPlanner(max_depth=3, max_simulations=20, timeout_ms=5000)
        initial_state = {"target": "test", "op": "CREATE", "goal": "add", "depth": 0, "taken_actions": []}
        planner.search(initial_state, simple_action_generator, simple_reward_function)
        assert planner.depth_reached >= 0

    def test_deterministic_with_same_seed(self, simple_action_generator, simple_reward_function):
        """Same seed should produce identical results."""
        import random

        initial_state = {"target": "test", "op": "CREATE", "goal": "add", "depth": 0, "taken_actions": []}

        # Run same search twice with same seed
        random.seed(42)
        planner1 = MCTSPlanner(max_depth=2, max_simulations=5, timeout_ms=5000)
        result1 = planner1.search(initial_state, simple_action_generator, simple_reward_function)

        random.seed(42)
        planner2 = MCTSPlanner(max_depth=2, max_simulations=5, timeout_ms=5000)
        result2 = planner2.search(initial_state, simple_action_generator, simple_reward_function)

        # Results should be identical
        assert result1 == result2
