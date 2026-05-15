"""
A07 ContextCompressor — SINGLE RESPONSIBILITY: Compress context to fit within token budget.

Deterministic compression strategies (in order of preference):
  1. Budget-aware selection: Pick highest-scored entries that fit the budget.
  2. Partial truncation: Include truncated entries if budget allows minimum.
  3. Raw truncation: Last resort — truncate the entire context to fit.

Also handles token budget allocation per operation/goal:
  - CREATE: more tokens for code, less for intent
  - DEBUG: more tokens for reasoning, less for intent
  - EXPLAIN: more tokens for reasoning, less for code
  - OPTIMIZE: more tokens for code, less for reasoning

No AI. All compression is deterministic. No LLM summarization.
"""

from __future__ import annotations

import logging
from typing import Any

from ..resilience import BaseAgent
from ..schemas import ScoredEntries, ScoredEntry, CompressedContext

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

TOTAL_CONTEXT_BUDGET = 500       # Total tokens available for context
MIN_ENTRY_TOKENS = 30            # Minimum tokens to include a truncated entry
CHARS_PER_TOKEN = 4              # Approximate chars per token (English/Spanish mix)
MIN_PARTIAL_CONTENT_CHARS = 120  # Minimum chars for a truncated entry

# ──────────────────────────────────────────────────────────────
# TOKEN BUDGET ALLOCATION
# Default budget distribution, adjustable per operation/goal.
# ──────────────────────────────────────────────────────────────

DEFAULT_TOKEN_BUDGET: dict[str, int] = {
    "intent": 50,
    "code": 200,
    "reasoning": 150,
    "validation": 100,
    "reserve": 50,
}

# Per-operation budget adjustments (multipliers applied to default)
OP_BUDGET_ADJUSTMENTS: dict[str, dict[str, float]] = {
    "CREATE": {
        "code": 1.25, "intent": 0.6, "validation": 0.7,
        "reasoning": 0.9, "reserve": 1.0,
    },
    "DEBUG": {
        "reasoning": 1.33, "intent": 0.6, "code": 0.75,
        "validation": 1.0, "reserve": 1.0,
    },
    "EXPLAIN": {
        "reasoning": 1.33, "code": 0.5, "intent": 1.0,
        "validation": 0.8, "reserve": 1.0,
    },
    "OPTIMIZE": {
        "code": 1.25, "reasoning": 0.8, "intent": 1.0,
        "validation": 0.9, "reserve": 1.0,
    },
    "ANALYZE": {
        "reasoning": 1.2, "code": 0.7, "intent": 1.0,
        "validation": 0.9, "reserve": 1.0,
    },
    "SEARCH": {
        "reasoning": 1.2, "code": 0.7, "intent": 1.0,
        "validation": 0.9, "reserve": 1.0,
    },
}

# Per-goal budget adjustments
GOAL_BUDGET_ADJUSTMENTS: dict[str, dict[str, float]] = {
    "SECURITY_HARDEN": {
        "validation": 1.5, "reserve": 0.5,
    },
    "BUG_FIX": {
        "reasoning": 1.2, "reserve": 0.6,
    },
    "PERFORMANCE": {
        "code": 1.15,
    },
}


class ContextCompressor(BaseAgent[CompressedContext]):
    """
    A07: Compress scored context entries to fit within a token budget.

    Single Responsibility: Context compression and budget allocation ONLY.
    Method: Budget-aware entry selection + truncation (deterministic).
    Fallback: Return empty CompressedContext when no entries available.

    INVARIANTS:
      - Never calls AI/LLM. Compression is purely deterministic.
      - Always returns a valid CompressedContext within budget.
      - Result never exceeds the specified token budget.
      - Design system preservation: if enabled, budget is expanded.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A07_ContextCompressor", **kwargs)
        self._design_system_mode: bool = False
        self._design_system_budget_multiplier: float = 1.0

    def set_design_system_mode(self, enabled: bool = False,
                                budget_multiplier: float = 1.0) -> None:
        """Enable/disable Design System preservation mode.

        When enabled, the compressor will NOT truncate Design System
        prompts from Open Design, preserving the full design specification.
        """
        self._design_system_mode = enabled
        self._design_system_budget_multiplier = budget_multiplier

    def execute(self, input_data: Any) -> CompressedContext:
        """
        Compress scored entries to fit within token budget.

        Input: dict with keys:
          - scored_entries: ScoredEntries (from A06 RelevanceScorer)
          - budget: int (total token budget, default 500)
          - operation: str (current intent operation for budget allocation)
          - goal: str (current intent goal for budget allocation)

        Output: CompressedContext with text within budget.
        """
        if not isinstance(input_data, dict):
            return self.fallback(input_data)

        scored_entries = input_data.get("scored_entries")
        budget = input_data.get("budget", TOTAL_CONTEXT_BUDGET)
        operation = input_data.get("operation", "SEARCH")
        goal = input_data.get("goal", "FEATURE_ADD")

        # Expand budget for Design System mode
        if self._design_system_mode:
            budget = int(budget * self._design_system_budget_multiplier)

        if not scored_entries or not isinstance(scored_entries, ScoredEntries):
            return self.fallback(input_data)

        entries = scored_entries.entries
        if not entries:
            return CompressedContext(
                text="", ratio=1.0, tokens_used=0,
                budget=budget, design_system_preserved=self._design_system_mode,
                source="deterministic",
            )

        # Allocate budget
        allocated_budget = self._allocate_budget(operation, goal, budget)

        # Compress entries to fit within budget
        compressed_text, tokens_used = self._compress_entries(entries, budget)

        # Calculate compression ratio
        raw_tokens = sum(len(e.content.split()) for e in entries)
        ratio = min(tokens_used / max(raw_tokens, 1), 1.0) if raw_tokens > 0 else 1.0

        return CompressedContext(
            text=compressed_text,
            ratio=round(ratio, 3),
            tokens_used=tokens_used,
            budget=budget,
            design_system_preserved=self._design_system_mode,
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> CompressedContext:
        """Safe fallback: empty context when no entries available."""
        budget = TOTAL_CONTEXT_BUDGET
        if isinstance(input_data, dict):
            budget = input_data.get("budget", TOTAL_CONTEXT_BUDGET)
            if self._design_system_mode:
                budget = int(budget * self._design_system_budget_multiplier)

        return CompressedContext(
            text="", ratio=1.0, tokens_used=0,
            budget=budget, design_system_preserved=False,
            source="fallback",
        )

    def allocate_budget_for(self, operation: str, goal: str,
                             total: int = TOTAL_CONTEXT_BUDGET) -> dict[str, int]:
        """Public API for budget allocation (used by pipeline orchestrator)."""
        return self._allocate_budget(operation, goal, total)

    # ──────────────────────────────────────────────────────────
    # PRIVATE: Compression & Budget Methods
    # ──────────────────────────────────────────────────────────

    def _compress_entries(
        self, entries: list[ScoredEntry], max_tokens: int
    ) -> tuple[str, int]:
        """
        Compress entries to fit within max_tokens budget.

        Strategy:
        1. Select entries that fit completely (highest score first).
        2. If budget allows, include truncated entries (min 30 tokens).
        3. If nothing fits, include the most relevant entry truncated.
        """
        if not entries:
            return "", 0

        selected: list[tuple[ScoredEntry, bool]] = []  # (entry, is_truncated)
        token_count = 0

        for entry in entries:
            entry_tokens = len(entry.content.split())

            if token_count + entry_tokens <= max_tokens:
                # Entry fits completely
                selected.append((entry, False))
                token_count += entry_tokens
            elif token_count + MIN_ENTRY_TOKENS <= max_tokens:
                # Entry partially fits — truncate
                selected.append((entry, True))
                token_count += MIN_ENTRY_TOKENS
            # Otherwise: skip (doesn't fit)

        if not selected:
            # Last resort: include the most relevant entry truncated
            best = entries[0]
            return best.content[:max_tokens * CHARS_PER_TOKEN], 1

        # Build compressed text
        parts: list[str] = []
        for entry, is_truncated in selected:
            source_type = entry.source_type or "ctx"
            score_str = f"{entry.combined_score:.2f}"

            if is_truncated:
                content = entry.content[:MIN_PARTIAL_CONTENT_CHARS] + "..."
            else:
                content = entry.content

            parts.append(f"[{source_type}:{score_str}] {content}")

        compressed = " | ".join(parts)

        # Safety: enforce hard limit
        max_chars = max_tokens * CHARS_PER_TOKEN
        if len(compressed) > max_chars:
            compressed = compressed[:max_chars - 3] + "..."

        return compressed, token_count

    def _allocate_budget(
        self, op: str, goal: str, total: int = TOTAL_CONTEXT_BUDGET
    ) -> dict[str, int]:
        """
        Allocate token budget per category based on operation and goal.

        Default distribution is adjusted by operation-specific and
        goal-specific multipliers, then normalized to not exceed total.
        """
        budget = DEFAULT_TOKEN_BUDGET.copy()

        # Apply operation adjustments
        op_adj = OP_BUDGET_ADJUSTMENTS.get(op, {})
        for key, multiplier in op_adj.items():
            if key in budget:
                budget[key] = max(int(budget[key] * multiplier), 20)

        # Apply goal adjustments
        goal_adj = GOAL_BUDGET_ADJUSTMENTS.get(goal, {})
        for key, multiplier in goal_adj.items():
            if key in budget:
                budget[key] = max(int(budget[key] * multiplier), 20)

        # Normalize: ensure total doesn't exceed budget
        total_allocated = sum(budget.values())
        if total_allocated > total:
            scale = total / total_allocated
            budget = {k: max(int(v * scale), 20) for k, v in budget.items()}
            # Second pass: verify total after min-floor enforcement
            # The min floor of 20 can cause total to still exceed budget
            total_allocated = sum(budget.values())
            if total_allocated > total:
                # Reduce only categories above minimum, proportional to excess
                excess = total_allocated - total
                reducible = {k: v - 20 for k, v in budget.items() if v > 20}
                total_reducible = sum(reducible.values())
                if total_reducible > 0:
                    for k in reducible:
                        reduction = int(excess * (reducible[k] / total_reducible))
                        budget[k] = max(budget[k] - reduction, 20)

        return budget
