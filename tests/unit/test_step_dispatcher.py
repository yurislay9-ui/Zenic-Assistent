"""
Unit tests for StepDispatcher

Tests execute_step for various action types (ANALYZE_STRUCTURE,
GENERATE_CODE, REPLACE_AST_NODE, DELETE_AST_NODE, PATCH_FIX, etc.),
execute_plan_steps for multi-step plans, and handling of unknown step types.

Modularized into test_step_disp_parts/ sub-directory.
"""

# Re-export all test classes from sub-modules for backward compatibility
from .test_step_disp_parts import *

# Re-export fixtures so they're available when running via this facade
from .test_step_disp_parts.conftest import (
    make_step, make_intent, make_plan, mock_orchestrator, dispatcher,
)
