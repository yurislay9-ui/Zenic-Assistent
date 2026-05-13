"""
Unit tests for src/core/shared/types.py - Data Types & Payloads

Tests:
- OperationType constants
- GoalType constants
- CriticalityLevel constants
- RoutePath constants
- IntentPayload construction and defaults
- RoutingPayload construction and defaults
- PlanStep construction and defaults
- ExecutionPlan construction and defaults
- SandboxResult construction and defaults
- MerkleNode construction and defaults
- ChatMessage and ChatRequest construction
- criticality_to_int conversion
- criticality_to_path conversion
- criticality_to_str conversion
- CRITICALITY_* mapping completeness
- __all__ completeness
"""

from .test_shared_types_parts import *  # noqa: F401,F403
from .test_shared_types_parts import __all__  # noqa: F401
