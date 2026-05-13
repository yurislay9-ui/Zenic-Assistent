"""
Zenic-Agents - Exception Taxonomy (Phase C2)

Unified exception taxonomy for the system. Defines exception categories,
severity levels, context containers, and helper functions for mapping
Python exceptions and confidence scores to structured exception types.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Type

logger = logging.getLogger(__name__)

__all__ = [
    "ExceptionCategory",
    "ExceptionSeverity",
    "ExceptionContext",
    "ZenicException",
    "categorize_error",
    "severity_from_confidence",
]


# ── Enums ─────────────────────────────────────────────────────


class ExceptionCategory(str, Enum):
    """Classification of exception origin / domain."""

    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    DATA_CONFLICT = "DATA_CONFLICT"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    BUSINESS_RULE_VIOLATION = "BUSINESS_RULE_VIOLATION"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    TIMEOUT = "TIMEOUT"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    DEGRADATION_TRIGGER = "DEGRADATION_TRIGGER"


class ExceptionSeverity(str, Enum):
    """Severity level of an exception signal."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"

    @property
    def numeric(self) -> int:
        """Return a numeric value for comparison (higher = more severe)."""
        return {
            ExceptionSeverity.INFO: 0,
            ExceptionSeverity.WARNING: 1,
            ExceptionSeverity.ERROR: 2,
            ExceptionSeverity.CRITICAL: 3,
            ExceptionSeverity.FATAL: 4,
        }[self]


# ── Dataclasses ───────────────────────────────────────────────


@dataclass
class ExceptionContext:
    """Structured context carried alongside every exception signal."""

    source: str
    category: ExceptionCategory
    severity: ExceptionSeverity
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    confidence_score: float = 0.0
    tenant_id: str = ""
    timestamp: str = ""
    correlation_id: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.correlation_id:
            self.correlation_id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the context to a plain dictionary."""
        return {
            "source": self.source,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "confidence_score": self.confidence_score,
            "tenant_id": self.tenant_id,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
        }


# ── Exception class ───────────────────────────────────────────


class ZenicException(Exception):
    """Base exception wrapping an :class:`ExceptionContext`.

    Provides a ``.context`` property and a readable ``__str__`` that
    includes category, severity, source, and correlation id.
    """

    def __init__(self, context: ExceptionContext) -> None:
        self._context = context
        super().__init__(context.message)

    @property
    def context(self) -> ExceptionContext:
        """Return the structured exception context."""
        return self._context

    def __str__(self) -> str:
        return (
            f"[{self._context.category.value}:{self._context.severity.value}] "
            f"{self._context.message} "
            f"(source={self._context.source}, "
            f"correlation_id={self._context.correlation_id})"
        )

    def __repr__(self) -> str:
        return f"ZenicException({self._context!r})"


# ── Helper functions ──────────────────────────────────────────

# Mapping from Python exception types to ExceptionCategory.
# Order matters: more specific types are listed first so that MRO
# walking hits them before their base classes.
_ERROR_CATEGORY_MAP: Dict[Type[Exception], ExceptionCategory] = {
    PermissionError: ExceptionCategory.PERMISSION_DENIED,
    TimeoutError: ExceptionCategory.TIMEOUT,
    MemoryError: ExceptionCategory.RESOURCE_EXHAUSTED,
    BufferError: ExceptionCategory.RESOURCE_EXHAUSTED,
    RecursionError: ExceptionCategory.RESOURCE_EXHAUSTED,
    FileNotFoundError: ExceptionCategory.SYSTEM_ERROR,
    IsADirectoryError: ExceptionCategory.SYSTEM_ERROR,
    NotADirectoryError: ExceptionCategory.SYSTEM_ERROR,
    ConnectionError: ExceptionCategory.SYSTEM_ERROR,
    ConnectionResetError: ExceptionCategory.SYSTEM_ERROR,
    ConnectionAbortedError: ExceptionCategory.SYSTEM_ERROR,
    ConnectionRefusedError: ExceptionCategory.SYSTEM_ERROR,
    BrokenPipeError: ExceptionCategory.SYSTEM_ERROR,
    ValueError: ExceptionCategory.DATA_CONFLICT,
    KeyError: ExceptionCategory.DATA_CONFLICT,
    TypeError: ExceptionCategory.DATA_CONFLICT,
    IOError: ExceptionCategory.SYSTEM_ERROR,
    OSError: ExceptionCategory.SYSTEM_ERROR,
    RuntimeError: ExceptionCategory.SYSTEM_ERROR,
    StopIteration: ExceptionCategory.SYSTEM_ERROR,
    ArithmeticError: ExceptionCategory.DATA_CONFLICT,
    ZeroDivisionError: ExceptionCategory.DATA_CONFLICT,
    OverflowError: ExceptionCategory.DATA_CONFLICT,
    FloatingPointError: ExceptionCategory.DATA_CONFLICT,
    UnicodeError: ExceptionCategory.DATA_CONFLICT,
    AttributeError: ExceptionCategory.DATA_CONFLICT,
    ImportError: ExceptionCategory.SYSTEM_ERROR,
    ModuleNotFoundError: ExceptionCategory.SYSTEM_ERROR,
}


def categorize_error(error: Exception) -> ExceptionCategory:
    """Map a Python exception to an :class:`ExceptionCategory`.

    Walks the MRO of the exception type so that the most-specific
    match in ``_ERROR_CATEGORY_MAP`` wins.  Falls back to
    :attr:`ExceptionCategory.SYSTEM_ERROR` when no mapping is found.
    """
    for cls in type(error).__mro__:
        if cls in _ERROR_CATEGORY_MAP:
            return _ERROR_CATEGORY_MAP[cls]
    return ExceptionCategory.SYSTEM_ERROR


def severity_from_confidence(confidence: float) -> ExceptionSeverity:
    """Derive an :class:`ExceptionSeverity` from a confidence score.

    Higher confidence means the system is more certain of its output,
    so the severity is *lower*.  Low confidence signals a problem.

    Thresholds:
        >= 0.7  → INFO
        >= 0.4  → WARNING
        >= 0.2  → ERROR
        >= 0.1  → CRITICAL
        <  0.1  → FATAL
    """
    if confidence >= 0.7:
        return ExceptionSeverity.INFO
    if confidence >= 0.4:
        return ExceptionSeverity.WARNING
    if confidence >= 0.2:
        return ExceptionSeverity.ERROR
    if confidence >= 0.1:
        return ExceptionSeverity.CRITICAL
    return ExceptionSeverity.FATAL
