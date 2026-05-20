"""
ZENIC-AGENTS — Types for the DynamicChainComposer module.

Enums, dataclasses, persistence paths, and the module logger.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Persistence paths
# ---------------------------------------------------------------------------

_DB_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "db")
_DB_PATH = os.path.join(_DB_DIR, "chain_composer.sqlite")

# ---------------------------------------------------------------------------
#  Enums
# ---------------------------------------------------------------------------


class ChainStepType(str, Enum):
    """Types of steps in a composed chain."""

    TRIGGER = "trigger"
    CONDITION = "condition"
    ACTION = "action"
    NOTIFICATION = "notification"
    DELAY = "delay"
    SUB_CHAIN = "sub_chain"


class ChainStatus(str, Enum):
    """Lifecycle status of a composed chain."""

    DRAFT = "draft"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
#  Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ChainStep:
    """A single executable step within a composed chain."""

    step_id: str = ""
    step_type: ChainStepType = ChainStepType.ACTION
    config: dict[str, Any] = field(default_factory=dict)
    next_step_id: str = ""
    condition_expr: str = ""
    timeout_ms: int = 30000
    retry_count: int = 3


@dataclass
class ComposedChain:
    """An instantiated, executable workflow chain."""

    chain_id: str = ""
    name: str = ""
    description: str = ""
    steps: list[ChainStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    tenant_id: str = ""
    created_at: float = 0.0
    status: ChainStatus = ChainStatus.DRAFT


@dataclass
class ChainStepResult:
    """Result of executing a single chain step."""

    step_id: str = ""
    success: bool = False
    output: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    retry_count: int = 0
    error: str | None = None


@dataclass
class ChainExecutionResult:
    """Result of executing an entire chain."""

    chain_id: str = ""
    success: bool = False
    step_results: list[ChainStepResult] = field(default_factory=list)
    total_duration_ms: int = 0
    failed_step: str | None = None
    error: str | None = None


@dataclass
class ChainValidationResult:
    """Validation outcome for a composed chain."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
