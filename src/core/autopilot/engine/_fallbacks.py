"""ZENIC-AGENTS - Autopilot Engine: Fallback/Mock Classes

Provides no-op and permissive fallback implementations for executor
subsystems (ImpactPreviewEngine, SafetyGate, ActionDispatcher) when
the real implementations are unavailable due to missing dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


# ──────────────────────────────────────────────────────────────
#  IMPACT PREVIEW FALLBACKS
# ──────────────────────────────────────────────────────────────

class _NoOpImpactPreview:
    """Fallback ImpactPreviewEngine when the real one is unavailable."""

    def preview_action(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Return a minimal impact preview with conservative risk score."""
        return _MockImpactPreview(action_type=action_type, risk_score=0.3)


@dataclass
class _MockImpactPreview:
    """Minimal impact preview for fallback mode."""

    action_type: str = ""
    risk_score: float = 0.3

    def to_dict(self) -> Dict[str, Any]:
        return {"action_type": self.action_type, "risk_score": self.risk_score}


# ──────────────────────────────────────────────────────────────
#  SAFETY GATE FALLBACKS
# ──────────────────────────────────────────────────────────────

class _PermissiveSafetyFallback:
    """Fallback SafetyGate when the real one is unavailable.

    Returns ALLOW for all actions to avoid blocking the autopilot.
    """

    def check(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Return ALLOW verdict for all actions."""
        return _MockSafetyResult()


@dataclass
class _MockSafetyResult:
    """Minimal safety result for fallback mode."""

    verdict: str = "ALLOW"

    def to_dict(self) -> Dict[str, Any]:
        return {"verdict": self.verdict}


# ──────────────────────────────────────────────────────────────
#  ACTION DISPATCHER FALLBACKS
# ──────────────────────────────────────────────────────────────

class _NoOpDispatcher:
    """Fallback ActionDispatcher when the real one is unavailable."""

    async def dispatch(self, request: Any) -> Any:
        """Return a success result without executing anything."""
        return _MockDispatchResult(success=True)


@dataclass
class _MockDispatchResult:
    """Minimal dispatch result for fallback mode."""

    success: bool = True
    action_id: str = ""
    safety_verdict: Any = None
    total_duration_ms: float = 0.0
