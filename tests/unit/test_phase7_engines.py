"""
ZENIC-AGENTS - Phase 7 Integration Tests

Tests for the three Phase 7 engines:
  1. ActionExecutor (8 real executors)
  2. LogicBuilder (30 composable blocks)
  3. AuthService (JWT + RBAC)
  4. Integration with AutomationEngine and Orchestrator
"""

from .test_phase7_parts import *  # noqa: F401,F403
from .test_phase7_parts import __all__  # noqa: F401
