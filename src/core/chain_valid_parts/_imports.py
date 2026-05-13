"""
Shared enums and data classes for chain_valid_parts.
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================
#  ENUMS
# ============================================================

class ValidationLevel(Enum):
    """Validation strictness levels."""
    LENIENT = "lenient"      # Only check critical issues
    STANDARD = "standard"    # Check compatibility + types
    STRICT = "strict"        # Check everything including performance hints


class RecoveryAction(Enum):
    """Actions to take when a chain step fails."""
    RETRY = "retry"          # Retry the failed step
    SKIP = "skip"            # Skip and continue
    FALLBACK = "fallback"    # Use fallback value
    ABORT = "abort"          # Stop chain execution
    ROLLBACK = "rollback"    # Rollback to last successful state


class ChainStatus(Enum):
    """Status of chain execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    PARTIAL = "partial"       # Completed but with some step failures


# ============================================================
#  DATA CLASSES
# ============================================================

@dataclass
class ValidationError:
    """A single validation issue."""
    level: str  # "error", "warning", "info"
    code: str   # "missing_input", "type_mismatch", etc.
    message: str
    block_name: str = ""
    block_index: int = -1


@dataclass
class ValidationResult:
    """Result of chain validation."""
    is_valid: bool = True
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    can_execute: bool = True  # True if chain can be attempted even with warnings

    def add_error(self, code: str, message: str, block_name: str = "", block_index: int = -1) -> None:
        self.errors.append(ValidationError("error", code, message, block_name, block_index))
        self.is_valid = False
        self.can_execute = False

    def add_warning(self, code: str, message: str, block_name: str = "", block_index: int = -1) -> None:
        self.warnings.append(ValidationError("warning", code, message, block_name, block_index))


@dataclass
class StepResult:
    """Result of a single step execution."""
    step_index: int
    block_name: str
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0
    snapshot_before: Dict[str, Any] = field(default_factory=dict)
    retried: bool = False
    recovered: bool = False
    recovery_action: Optional[RecoveryAction] = None


@dataclass
class ChainResult:
    """Result of a complete chain execution with full diagnostics."""
    status: ChainStatus = ChainStatus.PENDING
    final_data: Dict[str, Any] = field(default_factory=dict)
    step_results: List[StepResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    steps_completed: int = 0
    steps_failed: int = 0
    steps_skipped: int = 0
    rollback_count: int = 0
    validation: Optional[ValidationResult] = None
    error: str = ""
