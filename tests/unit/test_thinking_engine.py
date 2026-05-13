"""
ZENIC-AGENTS - ThinkingEngine Unit Tests

Tests for src/core/thinking_engine.py:
  - plan_generation (template identification, entity extraction)
  - select_template
  - customize_template (variable substitution)
  - reason (with and without AI)
  - evaluate_code (static analysis + AI)
  - decompose_problem (fallback)
  - design_architecture (fallback)
  - chain_of_thought
  - Stats
"""

from .test_thinking_parts import *
