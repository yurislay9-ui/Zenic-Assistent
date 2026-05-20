"""
Cost Accumulator — Types and helpers.

Contains CostCategory enum, DEFAULT_UNIT_COSTS, CostEntry dataclass,
and retry helper.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CostCategory(str, Enum):
    """Categories of operational cost."""

    LLM_TOKENS = "llm_tokens"
    API_CALLS = "api_calls"
    COMPUTE_TIME = "compute_time"
    HUMAN_TIME = "human_time"
    STORAGE = "storage"
    NETWORK = "network"


DEFAULT_UNIT_COSTS: Dict[CostCategory, float] = {
    CostCategory.LLM_TOKENS: 0.00003,
    CostCategory.API_CALLS: 0.001,
    CostCategory.COMPUTE_TIME: 0.05,
    CostCategory.HUMAN_TIME: 25.0,
    CostCategory.STORAGE: 0.023,
    CostCategory.NETWORK: 0.09,
}


@dataclass
class CostEntry:
    """A single recorded cost entry."""

    entry_id: str = ""
    action_id: str = ""
    category: CostCategory = CostCategory.LLM_TOKENS
    quantity: float = 0.0
    unit_cost: float = 0.0
    total_cost: float = 0.0
    currency: str = "USD"
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.entry_id:
            self.entry_id = uuid.uuid4().hex[:16]
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if self.total_cost == 0.0 and (self.quantity != 0.0 or self.unit_cost != 0.0):
            self.total_cost = round(self.quantity * self.unit_cost, 6)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "entry_id": self.entry_id,
            "action_id": self.action_id,
            "category": self.category.value,
            "quantity": self.quantity,
            "unit_cost": self.unit_cost,
            "total_cost": self.total_cost,
            "currency": self.currency,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


# ── Retry helper ─────────────────────────────────────────

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.1  # seconds


def _with_retry(fn, label: str = "CostAccumulator DB op"):
    """Execute *fn* with exponential-backoff retry (3 attempts)."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.debug(
                    "%s error (attempt %d/%d): %s — retrying in %.2fs",
                    label, attempt, _MAX_RETRIES, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "%s failed after %d attempts: %s", label, _MAX_RETRIES, exc,
                )
    if last_exc is not None:
        raise last_exc  # type: ignore[misc]
