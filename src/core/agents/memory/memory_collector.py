"""
A05 MemoryCollector — SINGLE RESPONSIBILITY: Collect relevant memory entries from all stores.

Deterministic collection from SmartMemory's 4 memory stores:
  1. Working Memory — current session context (most recent, highest priority)
  2. Long-term Memory — previously successful solutions (via semantic similarity)
  3. Episodic Memory — event history (errors, successes, transitions)
  4. Procedural Memory — learned patterns (success rates, reusable steps)

No AI. All collection is deterministic keyword/hash/metadata based.
"""

from __future__ import annotations

import time
import logging
from typing import Any

from ..resilience import BaseAgent
from ..schemas import MemoryEntries

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

MAX_ENTRIES_PER_STORE = 20       # Max entries to collect per store
RECENCY_DECAY_FACTOR = 0.95      # Exponential decay per 60 seconds
CONTENT_SNIPPET_LEN = 120        # Max chars per content snippet


class MemoryCollector(BaseAgent[MemoryEntries]):
    """
    A05: Collect relevant memory entries from all SmartMemory stores.

    Single Responsibility: Memory collection ONLY.
    Method: Deterministic retrieval from working/long-term/episodic/procedural stores.
    Fallback: Return empty MemoryEntries when SmartMemory is unavailable.

    INVARIANTS:
      - Never calls AI/LLM. Collection is purely deterministic.
      - Always returns a valid MemoryEntries (never raises).
      - Gracefully handles SmartMemory unavailability.
      - Each store collection is independent — failure of one doesn't block others.
    """

    def __init__(self, smart_memory=None, semantic_engine=None, **kwargs) -> None:
        super().__init__(name="A05_MemoryCollector", **kwargs)
        self._smart_memory = smart_memory
        self._semantic_engine = semantic_engine

    def wire(self, smart_memory=None, semantic_engine=None) -> None:
        """Inject dependencies post-creation (same pattern as original ContextAgent)."""
        if smart_memory is not None:
            self._smart_memory = smart_memory
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine

    def execute(self, input_data: Any) -> MemoryEntries:
        """
        Collect memory entries from all 4 stores.

        Input: dict with keys:
          - message: str (the user's current message/query)
          - operation: str (current intent operation, e.g., "CREATE")
          - goal: str (current intent goal, e.g., "FEATURE_ADD")

        Output: MemoryEntries with entries from all 4 stores.
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

        working = self._collect_working(operation, goal)
        long_term = self._collect_long_term(message, operation, goal)
        episodic = self._collect_episodic(operation, goal)
        procedural = self._collect_procedural(operation, goal)

        return MemoryEntries(
            working=working,
            long_term=long_term,
            episodic=episodic,
            procedural=procedural,
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> MemoryEntries:
        """Safe fallback: empty entries when SmartMemory is unavailable."""
        return MemoryEntries(
            working=[],
            long_term=[],
            episodic=[],
            procedural=[],
            source="fallback",
        )

    # ──────────────────────────────────────────────────────────
    # PRIVATE: Per-Store Collection Methods
    # ──────────────────────────────────────────────────────────

    def _collect_working(self, operation: str, goal: str) -> list[dict[str, Any]]:
        """Collect entries from working memory (current session context)."""
        entries: list[dict[str, Any]] = []
        now = time.time()

        try:
            working_entries = self._smart_memory._working_memory[:MAX_ENTRIES_PER_STORE]
        except (AttributeError, TypeError):
            return entries

        for entry in working_entries:
            try:
                age_seconds = now - entry.timestamp if entry.timestamp > 0 else 60
                recency = RECENCY_DECAY_FACTOR ** (age_seconds / 60.0)

                content = f"[{entry.operation}/{entry.goal}] Q:{entry.query[:60]}"
                if entry.response:
                    content += f" A:{entry.response[:80]}"

                entries.append({
                    "content": content[:CONTENT_SNIPPET_LEN],
                    "source": "working",
                    "operation": entry.operation,
                    "goal": entry.goal,
                    "importance": entry.importance,
                    "recency": recency,
                    "token_estimate": len(content.split()),
                })
            except Exception as e:
                logger.debug(f"A05: Working memory entry extraction failed: {e}")
                continue

        return entries

    def _collect_long_term(self, message: str, operation: str, goal: str) -> list[dict[str, Any]]:
        """Collect entries from long-term memory (previously successful solutions)."""
        entries: list[dict[str, Any]] = []

        if not message:
            return entries

        # Try semantic similarity search first (if SemanticEngine is available)
        if self._semantic_engine and self._semantic_engine.is_loaded:
            try:
                similar = self._smart_memory.find_similar_solutions(message, top_k=5)
                for sol in similar:
                    content = (
                        f"[{sol.get('operation', '')}/{sol.get('goal', '')}] "
                        f"{sol.get('solution', '')[:100]}"
                    )
                    entries.append({
                        "content": content[:CONTENT_SNIPPET_LEN],
                        "source": "long_term",
                        "operation": sol.get("operation", ""),
                        "goal": sol.get("goal", ""),
                        "importance": sol.get("importance", 0.5),
                        "recency": 0.5,  # No reliable timestamp, assume mid
                        "relevance_score": sol.get("similarity", 0.5),
                        "token_estimate": len(content.split()),
                    })
            except Exception as e:
                logger.debug(f"A05: Long-term semantic search failed: {e}")

        return entries[:MAX_ENTRIES_PER_STORE]

    def _collect_episodic(self, operation: str, goal: str) -> list[dict[str, Any]]:
        """Collect entries from episodic memory (event history)."""
        entries: list[dict[str, Any]] = []

        # Fetch error episodes for DEBUG/BUG_FIX
        if operation in ("DEBUG",) or goal in ("BUG_FIX",):
            try:
                episodes = self._smart_memory.find_episodes(event_type="error", limit=3)
                for ep in episodes:
                    content = (
                        f"[error/{ep.get('event_type', '')}] "
                        f"{ep.get('description', '')[:80]}"
                    )
                    entries.append({
                        "content": content[:CONTENT_SNIPPET_LEN],
                        "source": "episodic",
                        "event_type": ep.get("event_type", ""),
                        "importance": ep.get("importance", 0.5),
                        "recency": 0.4,
                        "token_estimate": len(content.split()),
                    })
            except Exception as e:
                logger.debug(f"A05: Episodic memory collection failed: {e}")

        return entries[:MAX_ENTRIES_PER_STORE]

    def _collect_procedural(self, operation: str, goal: str) -> list[dict[str, Any]]:
        """Collect entries from procedural memory (learned patterns)."""
        entries: list[dict[str, Any]] = []

        # Fetch procedural patterns relevant to CREATE/OPTIMIZE
        if operation in ("CREATE", "OPTIMIZE", "REFACTOR"):
            try:
                patterns = self._smart_memory.find_patterns(
                    min_success_rate=0.6, limit=3
                )
                for pat in patterns:
                    content = (
                        f"[pattern/{pat.get('pattern_type', '')}] "
                        f"{pat.get('description', '')[:80]}"
                    )
                    entries.append({
                        "content": content[:CONTENT_SNIPPET_LEN],
                        "source": "procedural",
                        "pattern_type": pat.get("pattern_type", ""),
                        "importance": pat.get("success_rate", 0.5),
                        "recency": 0.3,  # Patterns are more stable
                        "token_estimate": len(content.split()),
                    })
            except Exception as e:
                logger.debug(f"A05: Procedural memory collection failed: {e}")

        return entries[:MAX_ENTRIES_PER_STORE]
