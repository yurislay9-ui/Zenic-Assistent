"""
Dry-Run Executor — Types and helpers.

Contains DryRunOperation, DryRunResult dataclasses and retry logic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = None  # Avoid circular import; set by _mixin_core

import logging as _logging
logger = _logging.getLogger(__name__)


def _now_ts() -> str:
    """Return a high-resolution timestamp string."""
    return f"{time.time():.6f}"


def _retry(
    fn: Any,
    max_retries: int = 3,
    base_delay: float = 0.1,
    label: str = "dry_run",
) -> Any:
    """Execute *fn* with exponential-backoff retry.

    Delays: base_delay * 2^attempt  →  0.1s, 0.2s, 0.4s.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.debug(
                    "%s: retry %d/%d after %.2fs — %s",
                    label, attempt + 1, max_retries, delay, exc,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "%s: failed after %d attempts — %s",
                    label, max_retries, exc,
                )
    raise last_exc  # type: ignore[misc]


@dataclass
class DryRunOperation:
    """A single intercepted operation recorded during a dry-run.

    Attributes:
        operation_type: Category of the intercepted operation
            (e.g. ``"smtp"``, ``"http"``, ``"db"``, ``"file"``).
        target: The resource that would have been affected
            (e.g. URL, table name, file path, email address).
        would_affect: Dictionary describing what *would* change.
        timestamp: ISO-8601-like timestamp string.
    """

    operation_type: str
    target: str
    would_affect: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = _now_ts()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "operation_type": self.operation_type,
            "target": self.target,
            "would_affect": self.would_affect,
            "timestamp": self.timestamp,
        }


@dataclass
class DryRunResult:
    """Result of a full dry-run dispatch.

    Attributes:
        original_request: The dispatch request that was simulated.
        simulated_operations: List of operations that would have been performed.
        impact_preview: Dictionary representation of the impact preview.
        estimated_effects: Dictionary summarising estimated side-effects.
        would_succeed: Whether the action *would* succeed if executed for real.
        safety_verdict_would_be: The safety verdict the SafetyGate *would* return.
    """

    original_request: Dict[str, Any]
    simulated_operations: List[DryRunOperation] = field(default_factory=list)
    impact_preview: Dict[str, Any] = field(default_factory=dict)
    estimated_effects: Dict[str, Any] = field(default_factory=dict)
    would_succeed: bool = True
    safety_verdict_would_be: str = "ALLOW"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "original_request": self.original_request,
            "simulated_operations": [op.to_dict() for op in self.simulated_operations],
            "impact_preview": self.impact_preview,
            "estimated_effects": self.estimated_effects,
            "would_succeed": self.would_succeed,
            "safety_verdict_would_be": self.safety_verdict_would_be,
        }
