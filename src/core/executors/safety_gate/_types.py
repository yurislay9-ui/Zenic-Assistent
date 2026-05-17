"""
Safety Gate — Types, Rules, and Constants.

Contains SafetyVerdict, ActionCategory, SafetyRule, SafetyCheckResult,
and the deterministic SAFETY_RULES list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SafetyVerdict(str, Enum):
    """Safety gate verdict."""
    ALLOW = "ALLOW"
    CONFIRM = "CONFIRM"       # Requires user confirmation before proceeding
    APPROVE = "APPROVE"       # Requires higher-role approval
    DENY = "DENY"             # Absolutely denied — no override
    RATE_LIMITED = "RATE_LIMITED"  # Too many actions, slow down


class ActionCategory(str, Enum):
    """Classification of action risk level."""
    SAFE = "safe"               # Read-only, non-destructive
    MODERATE = "moderate"       # Write operations, single record
    DESTRUCTIVE = "destructive"  # Delete, drop, bulk operations
    FINANCIAL = "financial"      # Involves money, invoices, payments
    SYSTEM = "system"           # System-level changes


@dataclass
class SafetyRule:
    """A deterministic safety rule."""
    name: str
    category: ActionCategory
    pattern: str                           # Regex pattern to detect
    verdict: SafetyVerdict
    message: str
    compiled: Optional[re.Pattern] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.pattern:
            self.compiled = re.compile(self.pattern, re.IGNORECASE)  # nosemgrep: detect-non-literal-regexp


@dataclass
class SafetyCheckResult:
    """Result of a safety gate check."""
    verdict: SafetyVerdict
    category: ActionCategory
    reason: str
    rule_name: str
    requires_confirmation: bool = False
    requires_approval: bool = False
    risk_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
#  DETERMINISTIC SAFETY RULES
# ──────────────────────────────────────────────────────────────

SAFETY_RULES: List[SafetyRule] = [
    # ── DESTRUCTIVE: Mass deletions ────────────────────────────
    SafetyRule(
        name="mass_delete",
        category=ActionCategory.DESTRUCTIVE,
        pattern=r"\bDELETE\s+FROM\s+\w+\s*(?:WHERE\s+.+)?\s*;?\s*$",
        verdict=SafetyVerdict.CONFIRM,
        message="Mass DELETE detected — requires explicit confirmation",
    ),
    SafetyRule(
        name="drop_table",
        category=ActionCategory.DESTRUCTIVE,
        pattern=r"\bDROP\s+(TABLE|INDEX|VIEW|TRIGGER|DATABASE)\b",
        verdict=SafetyVerdict.DENY,
        message="DROP statement detected — absolutely denied for safety",
    ),
    SafetyRule(
        name="truncate_table",
        category=ActionCategory.DESTRUCTIVE,
        pattern=r"\bTRUNCATE\s+(TABLE\s+)?\w+",
        verdict=SafetyVerdict.DENY,
        message="TRUNCATE detected — denied, use DELETE with WHERE clause",
    ),
    SafetyRule(
        name="bulk_update",
        category=ActionCategory.DESTRUCTIVE,
        pattern=r"\bUPDATE\s+\w+\s+SET\s+.+(?:\s+WHERE\s+.+)?$",
        verdict=SafetyVerdict.CONFIRM,
        message="UPDATE without WHERE or bulk UPDATE — requires confirmation",
    ),
    # ── FINANCIAL: Money-related operations ────────────────────
    SafetyRule(
        name="invoice_create",
        category=ActionCategory.FINANCIAL,
        pattern=r"(?:invoice|factura|receipt|pago|payment)",
        verdict=SafetyVerdict.APPROVE,
        message="Financial document creation — requires approval",
    ),
    SafetyRule(
        name="payment_process",
        category=ActionCategory.FINANCIAL,
        pattern=r"(?:charge|cobro|refund|reembolso|transfer|transferencia)",
        verdict=SafetyVerdict.APPROVE,
        message="Payment processing — requires approval from financial role",
    ),
    SafetyRule(
        name="price_change",
        category=ActionCategory.FINANCIAL,
        pattern=r"(?:price|precio|discount|descuento|rate|tarifa).*(?:change|update|modify)",
        verdict=SafetyVerdict.APPROVE,
        message="Price modification — requires approval",
    ),
    # ── SYSTEM: System-level operations ────────────────────────
    SafetyRule(
        name="db_backup",
        category=ActionCategory.SYSTEM,
        pattern=r"\bbackup\b",
        verdict=SafetyVerdict.CONFIRM,
        message="Database backup operation — requires confirmation",
    ),
    SafetyRule(
        name="schema_migration",
        category=ActionCategory.SYSTEM,
        pattern=r"(?:ALTER\s+TABLE|CREATE\s+TABLE|ADD\s+COLUMN|DROP\s+COLUMN)",
        verdict=SafetyVerdict.APPROVE,
        message="Schema migration — requires admin approval",
    ),
    SafetyRule(
        name="cron_schedule",
        category=ActionCategory.SYSTEM,
        pattern=r"(?:cron|schedule|interval)",
        verdict=SafetyVerdict.CONFIRM,
        message="Scheduling operation — requires confirmation to avoid spam",
    ),
]
