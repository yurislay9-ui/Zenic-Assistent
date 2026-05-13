from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class PolicyEffect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    CONDITIONAL = "conditional"


class PolicyOperator(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    REGEX = "regex"


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
