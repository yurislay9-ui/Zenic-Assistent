from __future__ import annotations

try:
    from .types import (
        PolicyEffect, PolicyOperator, PolicyCondition,
        PolicyStatement, PolicyDocument,
    )
except ImportError:
    PolicyEffect = None  # type: ignore[assignment,misc]
    PolicyOperator = None  # type: ignore[assignment,misc]
    PolicyCondition = None  # type: ignore[assignment,misc]
    PolicyStatement = None  # type: ignore[assignment,misc]
    PolicyDocument = None  # type: ignore[assignment,misc]

try:
    from .engine import (
        PolicyEvaluationResult,
        PolicyCodeEngine,
        get_policy_code_engine,
        reset_policy_code_engine,
    )
except ImportError:
    PolicyEvaluationResult = None  # type: ignore[assignment,misc]
    PolicyCodeEngine = None  # type: ignore[assignment,misc]
    get_policy_code_engine = None  # type: ignore[assignment,misc]
    reset_policy_code_engine = None  # type: ignore[assignment,misc]

try:
    from .builtins import get_builtin_policies, install_builtin_policies
except ImportError:
    get_builtin_policies = None  # type: ignore[assignment,misc]
    install_builtin_policies = None  # type: ignore[assignment,misc]

__all__ = [
    "PolicyEffect", "PolicyOperator", "PolicyCondition",
    "PolicyStatement", "PolicyDocument",
    "PolicyEvaluationResult", "PolicyCodeEngine",
    "get_policy_code_engine", "reset_policy_code_engine",
    "get_builtin_policies", "install_builtin_policies",
]
