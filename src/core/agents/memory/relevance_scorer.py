"""
A06 RelevanceScorer — SINGLE RESPONSIBILITY: Score memory entries by relevance to current task.

Deterministic scoring using a weighted multi-factor formula:
  Score = w_importance * importance + w_recency * recency + w_relevance * relevance

Where:
  - importance: from the entry's stored importance value (0.0-1.0)
  - recency: exponential time decay (1.0 = just now, → 0.0 over time)
  - relevance: how well the entry's operation/goal matches the current task

Also handles deduplication: removes entries with near-identical content hashes.

No AI. All scoring is deterministic weighted computation.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from ..resilience import BaseAgent
from ..schemas import MemoryEntries, ScoredEntry, ScoredEntries

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# SCORING WEIGHTS
# ──────────────────────────────────────────────────────────────

# How much each factor contributes to the combined score
W_IMPORTANCE = 0.30
W_RECENCY = 0.30
W_RELEVANCE = 0.40

# How much operation match vs goal match weighs in relevance
W_OP_IN_RELEVANCE = 0.60
W_GOAL_IN_RELEVANCE = 0.40

# If an entry already has a similarity/relevance_score from semantic search,
# blend it with the heuristic relevance at this ratio
W_HEURISTIC_BLEND = 0.50

# ──────────────────────────────────────────────────────────────
# RELEVANCE MAPS
# How relevant is each stored operation/goal to the current one?
# These encode domain knowledge about which tasks benefit from
# recalling which types of past interactions.
# ──────────────────────────────────────────────────────────────

OP_RELEVANCE_WEIGHTS: dict[str, dict[str, float]] = {
    "CREATE": {
        "CREATE": 1.0, "REFACTOR": 0.6, "OPTIMIZE": 0.5,
        "DEBUG": 0.2, "SEARCH": 0.3, "ANALYZE": 0.4,
        "EXPLAIN": 0.2, "DELETE": 0.1,
    },
    "REFACTOR": {
        "REFACTOR": 1.0, "CREATE": 0.5, "OPTIMIZE": 0.7,
        "DEBUG": 0.3, "SEARCH": 0.3, "ANALYZE": 0.5,
        "EXPLAIN": 0.3, "DELETE": 0.1,
    },
    "DEBUG": {
        "DEBUG": 1.0, "REFACTOR": 0.4, "OPTIMIZE": 0.3,
        "CREATE": 0.2, "SEARCH": 0.5, "ANALYZE": 0.6,
        "EXPLAIN": 0.4, "DELETE": 0.1,
    },
    "OPTIMIZE": {
        "OPTIMIZE": 1.0, "REFACTOR": 0.7, "CREATE": 0.4,
        "DEBUG": 0.3, "SEARCH": 0.3, "ANALYZE": 0.6,
        "EXPLAIN": 0.3, "DELETE": 0.1,
    },
    "SEARCH": {
        "SEARCH": 1.0, "ANALYZE": 0.6, "EXPLAIN": 0.5,
        "CREATE": 0.3, "DEBUG": 0.4, "REFACTOR": 0.2,
        "OPTIMIZE": 0.2, "DELETE": 0.1,
    },
    "ANALYZE": {
        "ANALYZE": 1.0, "SEARCH": 0.6, "EXPLAIN": 0.5,
        "DEBUG": 0.5, "OPTIMIZE": 0.4, "REFACTOR": 0.3,
        "CREATE": 0.3, "DELETE": 0.1,
    },
    "EXPLAIN": {
        "EXPLAIN": 1.0, "ANALYZE": 0.5, "SEARCH": 0.5,
        "DEBUG": 0.3, "REFACTOR": 0.2, "OPTIMIZE": 0.2,
        "CREATE": 0.2, "DELETE": 0.1,
    },
    "DELETE": {
        "DELETE": 1.0, "REFACTOR": 0.5, "DEBUG": 0.3,
        "SEARCH": 0.2, "ANALYZE": 0.2, "CREATE": 0.1,
        "OPTIMIZE": 0.1, "EXPLAIN": 0.1,
    },
}

GOAL_RELEVANCE_WEIGHTS: dict[str, dict[str, float]] = {
    "FEATURE_ADD": {
        "FEATURE_ADD": 1.0, "PERFORMANCE": 0.5, "SECURITY_HARDEN": 0.4,
        "BUG_FIX": 0.3, "READABILITY": 0.3, "COMPLEXITY_REDUCTION": 0.4,
        "MODERN_PATTERN": 0.5,
    },
    "BUG_FIX": {
        "BUG_FIX": 1.0, "SECURITY_HARDEN": 0.6, "PERFORMANCE": 0.3,
        "FEATURE_ADD": 0.2, "READABILITY": 0.3, "COMPLEXITY_REDUCTION": 0.3,
        "MODERN_PATTERN": 0.2,
    },
    "SECURITY_HARDEN": {
        "SECURITY_HARDEN": 1.0, "BUG_FIX": 0.6, "PERFORMANCE": 0.2,
        "FEATURE_ADD": 0.3, "READABILITY": 0.3, "COMPLEXITY_REDUCTION": 0.3,
        "MODERN_PATTERN": 0.4,
    },
    "PERFORMANCE": {
        "PERFORMANCE": 1.0, "COMPLEXITY_REDUCTION": 0.7, "MODERN_PATTERN": 0.5,
        "FEATURE_ADD": 0.3, "BUG_FIX": 0.3, "SECURITY_HARDEN": 0.2,
        "READABILITY": 0.4,
    },
    "READABILITY": {
        "READABILITY": 1.0, "COMPLEXITY_REDUCTION": 0.7, "MODERN_PATTERN": 0.6,
        "FEATURE_ADD": 0.3, "BUG_FIX": 0.2, "SECURITY_HARDEN": 0.2,
        "PERFORMANCE": 0.3,
    },
    "COMPLEXITY_REDUCTION": {
        "COMPLEXITY_REDUCTION": 1.0, "READABILITY": 0.7, "MODERN_PATTERN": 0.6,
        "PERFORMANCE": 0.5, "REFACTOR": 0.8, "FEATURE_ADD": 0.3,
        "BUG_FIX": 0.2, "SECURITY_HARDEN": 0.2,
    },
    "MODERN_PATTERN": {
        "MODERN_PATTERN": 1.0, "COMPLEXITY_REDUCTION": 0.6, "READABILITY": 0.5,
        "FEATURE_ADD": 0.4, "PERFORMANCE": 0.4, "SECURITY_HARDEN": 0.3,
        "BUG_FIX": 0.2,
    },
}

# Default relevance for unknown operations/goals
DEFAULT_RELEVANCE = 0.1

# Deduplication: content similarity threshold for hash comparison
DEDUP_CONTENT_PREFIX_LEN = 40  # First N chars for hash


class RelevanceScorer(BaseAgent[ScoredEntries]):
    """
    A06: Score memory entries by relevance to the current task.

    Single Responsibility: Scoring and deduplication ONLY.
    Method: Weighted multi-factor scoring (importance + recency + relevance).
    Fallback: Return empty ScoredEntries when no input provided.

    INVARIANTS:
      - Never calls AI/LLM. Scoring is purely deterministic.
      - Always returns a valid ScoredEntries (never raises).
      - Deduplication removes near-identical entries.
      - Entries are sorted by combined_score descending.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A06_RelevanceScorer", **kwargs)
        self._semantic_engine = None

    def execute(self, input_data: Any) -> ScoredEntries:
        """
        Score and deduplicate memory entries.

        Input: dict with keys:
          - memory_entries: MemoryEntries (from A05 MemoryCollector)
          - operation: str (current intent operation)
          - goal: str (current intent goal)

        Output: ScoredEntries with scored and deduplicated entries.
        """
        if not isinstance(input_data, dict):
            return self.fallback(input_data)

        memory_entries = input_data.get("memory_entries")
        operation = input_data.get("operation", "SEARCH")
        goal = input_data.get("goal", "FEATURE_ADD")

        if not memory_entries or not isinstance(memory_entries, MemoryEntries):
            return self.fallback(input_data)

        # Flatten all entries into a single list with source type
        all_entries = self._flatten_entries(memory_entries)

        if not all_entries:
            return ScoredEntries(entries=[], deduplicated=False, source="deterministic")

        # Score each entry
        scored = self._score_all(all_entries, operation, goal)

        # Deduplicate
        scored = self._deduplicate(scored)

        # Sort by combined_score descending
        scored.sort(key=lambda e: e.combined_score, reverse=True)

        return ScoredEntries(
            entries=scored,
            deduplicated=True,
            source="deterministic",
        )

    def wire(self, semantic_engine=None) -> None:
        """Inject SemanticEngine for similarity-based scoring."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine

    def fallback(self, input_data: Any) -> ScoredEntries:
        """Safe fallback: empty scored entries."""
        return ScoredEntries(entries=[], deduplicated=False, source="fallback")

    # ──────────────────────────────────────────────────────────
    # PRIVATE: Scoring & Dedup Methods
    # ──────────────────────────────────────────────────────────

    def _flatten_entries(self, memory_entries: MemoryEntries) -> list[dict[str, Any]]:
        """Flatten MemoryEntries into a list of dicts with source_type."""
        flat: list[dict[str, Any]] = []

        for store_name in ("working", "long_term", "episodic", "procedural"):
            store = getattr(memory_entries, store_name, [])
            for entry in store:
                entry_copy = dict(entry)
                entry_copy["source_type"] = store_name
                flat.append(entry_copy)

        return flat

    def _score_all(
        self, entries: list[dict[str, Any]], current_op: str, current_goal: str
    ) -> list[ScoredEntry]:
        """Score all entries using the weighted multi-factor formula."""
        scored: list[ScoredEntry] = []

        # Get relevance weight maps for current operation/goal
        op_weights = OP_RELEVANCE_WEIGHTS.get(current_op, {})
        goal_weights = GOAL_RELEVANCE_WEIGHTS.get(current_goal, {})

        for entry in entries:
            importance = float(entry.get("importance", 0.5))
            recency = float(entry.get("recency", 0.5))
            existing_relevance = float(entry.get("relevance_score", 0.0))

            # Compute heuristic relevance
            entry_op = entry.get("operation", "")
            entry_goal = entry.get("goal", "")
            op_rel = op_weights.get(entry_op, DEFAULT_RELEVANCE) if entry_op else DEFAULT_RELEVANCE
            goal_rel = goal_weights.get(entry_goal, DEFAULT_RELEVANCE) if entry_goal else DEFAULT_RELEVANCE
            heuristic_relevance = W_OP_IN_RELEVANCE * op_rel + W_GOAL_IN_RELEVANCE * goal_rel

            # Blend with existing semantic similarity score if available
            if existing_relevance > 0:
                relevance = W_HEURISTIC_BLEND * heuristic_relevance + W_HEURISTIC_BLEND * existing_relevance
            else:
                relevance = heuristic_relevance

            # Combined score
            combined = (
                W_IMPORTANCE * importance +
                W_RECENCY * recency +
                W_RELEVANCE * relevance
            )

            scored.append(ScoredEntry(
                content=entry.get("content", ""),
                importance=importance,
                recency=recency,
                relevance=relevance,
                combined_score=round(combined, 4),
                source_type=entry.get("source_type", ""),
            ))

        return scored

    def _deduplicate(self, entries: list[ScoredEntry]) -> list[ScoredEntry]:
        """
        Remove near-identical entries based on content prefix hash.

        Strategy: hash the first N characters of content. If two entries
        have the same hash, keep the one with the higher combined_score.
        """
        seen_hashes: dict[str, ScoredEntry] = {}

        for entry in entries:
            # Hash the content prefix for dedup
            prefix = entry.content[:DEDUP_CONTENT_PREFIX_LEN].lower().strip()
            content_hash = hashlib.md5(prefix.encode()).hexdigest()

            if content_hash in seen_hashes:
                # Keep the higher-scoring entry
                if entry.combined_score > seen_hashes[content_hash].combined_score:
                    seen_hashes[content_hash] = entry
            else:
                seen_hashes[content_hash] = entry

        return list(seen_hashes.values())
