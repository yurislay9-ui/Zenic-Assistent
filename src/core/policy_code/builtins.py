from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .types import (
    PolicyCondition,
    PolicyDocument,
    PolicyEffect,
    PolicyOperator,
    PolicyStatement,
)

if True:  # Keep import block together
    from .engine import PolicyCodeEngine, get_policy_code_engine


def get_builtin_policies() -> List[PolicyDocument]:
    """Return predefined built-in policy documents."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    policies: List[PolicyDocument] = []

    # 1. Deny destructive actions without approval
    policies.append(PolicyDocument(
        id="deny_destructive_without_approval",
        name="Deny Destructive Without Approval",
        version="1.0",
        statements=[
            PolicyStatement(
                id="deny_unapproved_delete",
                effect=PolicyEffect.DENY,
                resource="*",
                action="delete",
                conditions=[
                    PolicyCondition(
                        field="approved",
                        operator=PolicyOperator.EQ,
                        value=False,
                        description="Action must be approved",
                    ),
                    PolicyCondition(
                        field="action_type",
                        operator=PolicyOperator.IN,
                        value=["delete", "drop", "truncate", "destroy"],
                        description="Destructive action types",
                    ),
                ],
                priority=100,
                description="Deny destructive actions that lack approval",
            ),
        ],
        created_at=now,
        updated_at=now,
        enabled=True,
        metadata={"builtin": True, "category": "safety"},
    ))

    # 2. Allow all read operations
    policies.append(PolicyDocument(
        id="allow_read_only",
        name="Allow Read Operations",
        version="1.0",
        statements=[
            PolicyStatement(
                id="allow_reads",
                effect=PolicyEffect.ALLOW,
                resource="*",
                action="read",
                conditions=[],
                priority=10,
                description="Allow all read operations",
            ),
            PolicyStatement(
                id="allow_list",
                effect=PolicyEffect.ALLOW,
                resource="*",
                action="list",
                conditions=[],
                priority=10,
                description="Allow all list operations",
            ),
            PolicyStatement(
                id="allow_get",
                effect=PolicyEffect.ALLOW,
                resource="*",
                action="get",
                conditions=[],
                priority=10,
                description="Allow all get operations",
            ),
        ],
        created_at=now,
        updated_at=now,
        enabled=True,
        metadata={"builtin": True, "category": "read_access"},
    ))

    # 3. Rate limit financial operations
    policies.append(PolicyDocument(
        id="rate_limit_financial",
        name="Rate Limit Financial Operations",
        version="1.0",
        statements=[
            PolicyStatement(
                id="financial_rate_limit",
                effect=PolicyEffect.CONDITIONAL,
                resource="financial/*",
                action="*",
                conditions=[
                    PolicyCondition(
                        field="requests_per_minute",
                        operator=PolicyOperator.LTE,
                        value=30,
                        description="Max 30 financial requests per minute",
                    ),
                    PolicyCondition(
                        field="daily_amount",
                        operator=PolicyOperator.LTE,
                        value=100000,
                        description="Max 100k daily amount",
                    ),
                ],
                priority=50,
                description="Rate limit financial operations",
            ),
        ],
        created_at=now,
        updated_at=now,
        enabled=True,
        metadata={"builtin": True, "category": "financial"},
    ))

    # 4. Restrict sensitive ops outside business hours
    policies.append(PolicyDocument(
        id="restrict_off_hours",
        name="Restrict Off-Hours Operations",
        version="1.0",
        statements=[
            PolicyStatement(
                id="deny_sensitive_off_hours",
                effect=PolicyEffect.DENY,
                resource="sensitive/*",
                action="write",
                conditions=[
                    PolicyCondition(
                        field="hour_of_day",
                        operator=PolicyOperator.NOT_IN,
                        value=list(range(9, 18)),
                        description="Outside business hours (9-17)",
                    ),
                ],
                priority=80,
                description="Deny sensitive writes outside business hours",
            ),
        ],
        created_at=now,
        updated_at=now,
        enabled=True,
        metadata={"builtin": True, "category": "time_restriction"},
    ))

    # 5. Require MFA for admin actions
    policies.append(PolicyDocument(
        id="require_mfa_for_admin",
        name="Require MFA for Admin Actions",
        version="1.0",
        statements=[
            PolicyStatement(
                id="admin_mfa_required",
                effect=PolicyEffect.CONDITIONAL,
                resource="admin/*",
                action="*",
                conditions=[
                    PolicyCondition(
                        field="mfa_verified",
                        operator=PolicyOperator.EQ,
                        value=True,
                        description="MFA must be verified",
                    ),
                ],
                priority=90,
                description="Admin actions require MFA",
            ),
        ],
        created_at=now,
        updated_at=now,
        enabled=True,
        metadata={"builtin": True, "category": "authentication"},
    ))

    return policies


def install_builtin_policies(
    engine: Optional[PolicyCodeEngine] = None,
) -> List[str]:
    """Install all built-in policies into the engine."""
    eng = engine or get_policy_code_engine()
    installed: List[str] = []
    for policy in get_builtin_policies():
        try:
            existing = eng.get_policy(policy.id)
            if existing is None:
                eng.create_policy(policy)
                installed.append(policy.id)
        except Exception:
            pass
    return installed
