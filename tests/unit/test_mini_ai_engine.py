"""
Unit tests for MiniAIEngine - Qwen3-0.6B Semantic Copilot

Tests cover:
1. Fallback methods (no model needed)
2. Model loading/unloading lifecycle
3. All 7 bounded tasks (with model if available, fallback otherwise)
4. Response parsing (think block extraction)
5. Stats tracking
"""

from .test_mini_ai_parts import *
