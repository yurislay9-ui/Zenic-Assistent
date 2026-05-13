"""
ZENIC-AGENTS v1 — Layer 2: Memory & Context Agents

Each agent has EXACTLY ONE function:
  A05 MemoryCollector   — Collect relevant memory entries from all stores
  A06 RelevanceScorer   — Score memory entries by relevance to current task
  A07 ContextCompressor — Compress context to fit within token budget
  A08 ContextPrefetcher — Prefetch likely-needed memories proactively

All agents are 100% deterministic. No AI calls.
Fallback: Each agent returns a safe empty result when SmartMemory is unavailable.

Pipeline: A05 → A06 → A07 (serial), A08 (parallel with A05)
"""

from .memory_collector import MemoryCollector
from .relevance_scorer import RelevanceScorer
from .context_compressor import ContextCompressor
from .context_prefetcher import ContextPrefetcher

__all__ = [
    "MemoryCollector",
    "RelevanceScorer",
    "ContextCompressor",
    "ContextPrefetcher",
]
