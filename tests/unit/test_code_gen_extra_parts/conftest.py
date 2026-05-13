"""
Shared fixtures for test_code_gen_extra_parts sub-modules.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.code_generator import CodeGenerator
from src.core.shared.contracts import (
    IntentPayload, ExecutionPlan, PlanStep, OperationType, GoalType
)


@pytest.fixture
def code_gen():
    """Create a CodeGenerator with a mock orchestrator."""
    class MockOrchestrator:
        pass
    return CodeGenerator(MockOrchestrator())


@pytest.fixture
def create_intent():
    """Create a basic CREATE intent."""
    return IntentPayload(
        op=OperationType.CREATE, target="my_module.py",
        goal=GoalType.FEATURE_ADD, confidence=0.9, context="",
        raw_code="", language="python"
    )


@pytest.fixture
def security_intent():
    """Create a SECURITY_HARDEN intent."""
    return IntentPayload(
        op=OperationType.CREATE, target="secure_mod.py",
        goal=GoalType.SECURITY_HARDEN, confidence=0.95, context="",
        raw_code="", language="python"
    )


@pytest.fixture
def bugfix_intent():
    """Create a BUG_FIX intent with raw code."""
    return IntentPayload(
        op=OperationType.CREATE, target="buggy.py",
        goal=GoalType.BUG_FIX, confidence=0.85, context="",
        raw_code="def broken(): return 1/0", language="python"
    )


@pytest.fixture
def refactor_intent():
    """Create a REFACTOR intent."""
    return IntentPayload(
        op=OperationType.REFACTOR, target="old_code.py",
        goal=GoalType.READABILITY, confidence=0.8, context="",
        raw_code="def f(x): return x", language="python"
    )


@pytest.fixture
def debug_intent():
    """Create a DEBUG intent."""
    return IntentPayload(
        op=OperationType.DEBUG, target="debug_me.py",
        goal=GoalType.BUG_FIX, confidence=0.7, context="",
        raw_code="def crash(): raise Error", language="python"
    )
