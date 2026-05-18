"""
Impact Scorer — Types and helpers.

Contains ImpactScore dataclass, retry helper, and row conversion function.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ImpactScore:
    """Economic impact assessment for an alert, exception, or action."""

    score_id: str = ""
    source: str = ""
    source_id: str = ""
    impact_type: str = ""
    estimated_loss_if_no_action: float = 0.0
    estimated_gain_if_action: float = 0.0
    urgency_hours: float = 0.0
    impact_score: float = 0.0
    currency: str = "USD"
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.score_id:
            self.score_id = uuid.uuid4().hex[:16]
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if self.impact_score == 0.0 and (
            self.estimated_loss_if_no_action > 0
            or self.estimated_gain_if_action > 0
        ):
            self.impact_score = round(
                (self.estimated_loss_if_no_action + self.estimated_gain_if_action)
                / (self.urgency_hours + 1),
                4,
            )

    def net_impact(self) -> float:
        """Return net impact: gain if action taken minus loss if no action."""
        return round(self.estimated_gain_if_action - self.estimated_loss_if_no_action, 2)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "score_id": self.score_id,
            "source": self.source,
            "source_id": self.source_id,
            "impact_type": self.impact_type,
            "estimated_loss_if_no_action": self.estimated_loss_if_no_action,
            "estimated_gain_if_action": self.estimated_gain_if_action,
            "urgency_hours": self.urgency_hours,
            "impact_score": self.impact_score,
            "currency": self.currency,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


# ── Retry helper ─────────────────────────────────────────

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.1


def _with_retry(fn, label: str = "ImpactScorer DB op"):
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


# ── Row helper ────────────────────────────────────────────

def _row_to_score(row: tuple) -> ImpactScore:
    """Convert a DB row tuple to an ImpactScore dataclass."""
    meta: Dict[str, Any] = {}
    if row[10]:
        try:
            meta = json.loads(row[10])
        except (json.JSONDecodeError, TypeError):
            meta = {}

    return ImpactScore(
        score_id=row[0],
        source=row[1],
        source_id=row[2],
        impact_type=row[3],
        estimated_loss_if_no_action=float(row[4]),
        estimated_gain_if_action=float(row[5]),
        urgency_hours=float(row[6]),
        impact_score=float(row[7]),
        currency=row[8],
        timestamp=row[9],
        metadata=meta,
    )
