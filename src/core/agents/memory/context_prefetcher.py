"""
A08 ContextPrefetcher — SINGLE RESPONSIBILITY: Prefetch likely-needed memories proactively.

Deterministic prefetch based on operation/goal patterns:
  1. For DEBUG/BUG_FIX: preload error episodes and failed solutions.
  2. For CREATE/OPTIMIZE: preload successful patterns and similar solutions.
  3. For REFACTOR: preload modern patterns and complexity reduction tips.
  4. For SECURITY_HARDEN: preload vulnerability patterns and security checks.
  5. For all: preload recent similar queries from cache.

Hints are generated describing what was prefetched and why, so downstream
agents can make informed decisions about using the prefetched context.

No AI. All prefetching is deterministic based on operation/goal heuristics.
"""

from __future__ import annotations

import logging
from typing import Any

from ..resilience import BaseAgent
from ..schemas import PrefetchResult

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

MAX_PREFETCH_RESULTS = 5         # Max total prefetched items
MAX_SOLUTIONS_PER_PREFETCH = 2   # Max solutions to prefetch
MAX_EPISODES_PER_PREFETCH = 2    # Max episodes to prefetch
MAX_PATTERNS_PER_PREFETCH = 2    # Max patterns to prefetch
SOLUTION_SNIPPET_LEN = 150       # Max chars for solution snippets
EPISODE_SNIPPET_LEN = 100        # Max chars for episode snippets

# ──────────────────────────────────────────────────────────────
# PREFETCH STRATEGY MAP
# What to prefetch for each operation/goal combination.
# ──────────────────────────────────────────────────────────────

PREFETCH_STRATEGIES: dict[str, dict[str, list[str]]] = {
    "operation": {
        "CREATE": ["similar_solutions", "procedural_patterns"],
        "OPTIMIZE": ["similar_solutions", "procedural_patterns"],
        "REFACTOR": ["similar_solutions", "procedural_patterns"],
        "DEBUG": ["error_episodes", "similar_solutions"],
        "DELETE": ["similar_solutions"],
        "SEARCH": ["similar_solutions"],
        "ANALYZE": ["similar_solutions"],
        "EXPLAIN": ["similar_solutions"],
    },
    "goal": {
        "BUG_FIX": ["error_episodes", "similar_solutions"],
        "SECURITY_HARDEN": ["similar_solutions", "procedural_patterns"],
        "PERFORMANCE": ["procedural_patterns", "similar_solutions"],
        "FEATURE_ADD": ["similar_solutions", "procedural_patterns"],
        "COMPLEXITY_REDUCTION": ["procedural_patterns", "similar_solutions"],
        "MODERN_PATTERN": ["procedural_patterns", "similar_solutions"],
        "READABILITY": ["similar_solutions"],
    },
}


class ContextPrefetcher(BaseAgent[PrefetchResult]):
    """
    A08: Prefetch likely-needed memories proactively.

    Single Responsibility: Proactive memory prefetching ONLY.
    Method: Deterministic strategy selection based on operation/goal heuristics.
    Fallback: Return empty PrefetchResult when SmartMemory is unavailable.

    INVARIANTS:
      - Never calls AI/LLM. Prefetching is purely deterministic.
      - Always returns a valid PrefetchResult (never raises).
      - Total prefetched items never exceed MAX_PREFETCH_RESULTS.
      - Hints describe what was prefetched so downstream agents know.
      - Gracefully handles SmartMemory/SemanticEngine unavailability.
    """

    def __init__(self, smart_memory=None, semantic_engine=None, **kwargs) -> None:
        super().__init__(name="A08_ContextPrefetcher", **kwargs)
        self._smart_memory = smart_memory
        self._semantic_engine = semantic_engine

    def wire(self, smart_memory=None, semantic_engine=None) -> None:
        """Inject dependencies post-creation."""
        if smart_memory is not None:
            self._smart_memory = smart_memory
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine

    def execute(self, input_data: Any) -> PrefetchResult:
        """
        Prefetch memories likely needed for the current task.

        Input: dict with keys:
          - message: str (the user's current message/query)
          - operation: str (current intent operation, e.g., "CREATE")
          - goal: str (current intent goal, e.g., "FEATURE_ADD")
          - history: list (optional, recent interaction history)

        Output: PrefetchResult with prefetched items and hints.
        """
        if not self._smart_memory:
            return self.fallback(input_data)

        # Extract parameters
        if isinstance(input_data, dict):
            message = input_data.get("message", "")
            operation = input_data.get("operation", "SEARCH")
            goal = input_data.get("goal", "FEATURE_ADD")
        else:
            message = str(input_data) if input_data else ""
            operation = "SEARCH"
            goal = "FEATURE_ADD"

        # Determine what to prefetch based on operation and goal
        strategies = self._get_strategies(operation, goal)

        # Execute each strategy
        results: list[dict[str, Any]] = []
        hints: list[str] = []

        for strategy in strategies:
            fetched, hint = self._execute_strategy(strategy, message, operation, goal)
            if fetched:
                results.extend(fetched)
                hints.append(hint)

            # Respect global limit
            if len(results) >= MAX_PREFETCH_RESULTS:
                results = results[:MAX_PREFETCH_RESULTS]
                break

        return PrefetchResult(
            prefetched=results,
            hints=hints,
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> PrefetchResult:
        """Safe fallback: empty prefetch when SmartMemory is unavailable."""
        return PrefetchResult(prefetched=[], hints=[], source="fallback")

    # ──────────────────────────────────────────────────────────
    # PRIVATE: Strategy Methods
    # ──────────────────────────────────────────────────────────

    def _get_strategies(self, operation: str, goal: str) -> list[str]:
        """Determine which prefetch strategies to execute, preserving order."""
        op_strategies = PREFETCH_STRATEGIES["operation"].get(operation, [])
        goal_strategies = PREFETCH_STRATEGIES["goal"].get(goal, [])

        # Merge: operation strategies first, then goal strategies not already included
        seen = set(op_strategies)
        merged = list(op_strategies)
        for s in goal_strategies:
            if s not in seen:
                merged.append(s)
                seen.add(s)

        return merged

    def _execute_strategy(
        self, strategy: str, message: str, operation: str, goal: str
    ) -> tuple:
        """Execute a single prefetch strategy. Returns (results, hint)."""
        try:
            if strategy == "similar_solutions":
                return self._prefetch_solutions(message)
            elif strategy == "error_episodes":
                return self._prefetch_episodes(operation, goal)
            elif strategy == "procedural_patterns":
                return self._prefetch_patterns(operation)
            else:
                return [], ""
        except Exception as e:
            logger.debug(f"A08: Prefetch strategy '{strategy}' failed: {e}")
            return [], ""

    def _prefetch_solutions(self, message: str) -> tuple:
        """Prefetch similar solutions from long-term memory."""
        results: list[dict[str, Any]] = []

        if not message:
            return results, ""

        # Try semantic search first (better quality)
        if self._semantic_engine and self._semantic_engine.is_loaded:
            try:
                similar = self._smart_memory.find_similar_solutions(
                    message, top_k=MAX_SOLUTIONS_PER_PREFETCH
                )
                for sol in similar[:MAX_SOLUTIONS_PER_PREFETCH]:
                    results.append({
                        "type": "similar_solution",
                        "operation": sol.get("operation", ""),
                        "solution": sol.get("solution", "")[:SOLUTION_SNIPPET_LEN],
                        "similarity": sol.get("similarity", 0.0),
                    })
            except Exception as e:
                logger.debug(f"A08: Semantic solution prefetch failed: {e}")

        hint = f"Prefetched {len(results)} similar solutions" if results else ""
        return results, hint

    def _prefetch_episodes(self, operation: str, goal: str) -> tuple:
        """Prefetch error episodes for debugging tasks."""
        results: list[dict[str, Any]] = []

        try:
            episodes = self._smart_memory.find_episodes(
                event_type="error", limit=MAX_EPISODES_PER_PREFETCH
            )
            for ep in episodes[:MAX_EPISODES_PER_PREFETCH]:
                results.append({
                    "type": "error_episode",
                    "description": ep.get("description", "")[:EPISODE_SNIPPET_LEN],
                    "outcome": ep.get("outcome", ""),
                })
        except Exception as e:
            logger.debug(f"A08: Episode prefetch failed: {e}")

        hint = f"Prefetched {len(results)} error episodes for {operation}/{goal}" if results else ""
        return results, hint

    def _prefetch_patterns(self, operation: str) -> tuple:
        """Prefetch procedural patterns for creation/optimization tasks."""
        results: list[dict[str, Any]] = []

        try:
            patterns = self._smart_memory.find_patterns(
                min_success_rate=0.7, limit=MAX_PATTERNS_PER_PREFETCH
            )
            for pat in patterns[:MAX_PATTERNS_PER_PREFETCH]:
                results.append({
                    "type": "procedural_pattern",
                    "name": pat.get("pattern_name", ""),
                    "success_rate": pat.get("success_rate", 0.0),
                    "steps": pat.get("steps", [])[:3],
                })
        except Exception as e:
            logger.debug(f"A08: Pattern prefetch failed: {e}")

        hint = f"Prefetched {len(results)} procedural patterns for {operation}" if results else ""
        return results, hint
