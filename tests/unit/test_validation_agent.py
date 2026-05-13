"""
Unit tests for ValidationAgent.

Tests the agent that unifies ChainValidator + code quality checks:
  - Code validation (security patterns, quality patterns, Python AST)
  - Chain validation (block compatibility, completeness)
  - Config validation (JSON/YAML, common issues)
  - Risk score calculation
  - Fix suggestions
  - Correction loop (parse_response for LLM output)
  - Legacy compatibility (to_validation_result)
"""

from .test_validation_parts import *  # noqa: F401,F403
from .test_validation_parts import __all__  # noqa: F401
from .test_validation_parts.conftest import *  # noqa: F401,F403
