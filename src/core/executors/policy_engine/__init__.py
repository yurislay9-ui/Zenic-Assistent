"""
ZENIC-AGENTS — Policy-as-Code Engine

Re-exports all public names from the policy_engine package.
"""

from ._engine import PolicyEngine, get_policy_engine, reset_policy_engine
from ._evaluator import PolicyCondition
from ._types import ConditionOperator, PolicyAction, PolicyDecision, PolicyRule

__all__ = [
    # Enums
    "PolicyAction",
    "ConditionOperator",
    # Dataclasses
    "PolicyCondition",
    "PolicyRule",
    "PolicyDecision",
    # Engine
    "PolicyEngine",
    # Singleton
    "get_policy_engine",
    "reset_policy_engine",
]
