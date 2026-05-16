"""Policy Code type definitions.

Re-exports canonical enums from executors.policy_engine to avoid duplication.
The ConditionOperator and PolicyEffect enums live in executors.policy_engine
which is the single source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

# ─── Canonical enums (re-exported from executors) ──────────────────────
# Avoid duplication: import from the single source of truth.
from src.core.executors.policy_engine import (
    ConditionOperator as PolicyOperator,  # Re-aliased for backward compat
    PolicyAction as PolicyEffect,          # Re-aliased for backward compat
)

# Backward-compatible aliases:
# - PolicyOperator = ConditionOperator (same operators, different name)
# - PolicyEffect = PolicyAction (ALLOW/DENY/CONDITIONAL → unified with executors)
#
# NOTE: PolicyEffect values are now UPPERCASE ("ALLOW" vs "allow") matching
# the executor's canonical form. Code that relied on lowercase values should
# use .value.lower() if needed for wire-format compatibility.


@dataclass
class PolicyCondition:
    field: str
    operator: PolicyOperator
    value: Any = None
    description: str = ""


@dataclass
class PolicyStatement:
    id: str
    effect: PolicyEffect
    resource: str
    action: str
    conditions: List[PolicyCondition] = field(default_factory=list)
    priority: int = 0
    description: str = ""


@dataclass
class PolicyDocument:
    id: str
    name: str
    version: str = "1.0"
    statements: List[PolicyStatement] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
