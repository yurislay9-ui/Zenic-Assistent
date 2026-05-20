"""Types and constants for integrity."""

from __future__ import annotations
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

_SAFE_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


class IntegrityStatus(str, Enum):
    """Status of an integrity check."""
    VALID = "valid"
    TAMPERED = "tampered"
    MISSING = "missing"
    ERROR = "error"


@dataclass
class IntegrityCheckResult:
    """Result of an integrity verification check."""
    component: str
    status: IntegrityStatus
    expected_hash: str = ""
    actual_hash: str = ""
    message: str = ""
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = time.time()


# ── Singleton ─────────────────────────────────────────────

_integrity_verifier: Optional[Any] = None
