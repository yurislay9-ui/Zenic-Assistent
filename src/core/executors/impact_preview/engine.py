"""ZENIC-AGENTS - Impact Preview Engine

Simulates the effects of an action WITHOUT executing it, providing
a preview of what would happen if the action were carried out.

All operations are strictly READ-ONLY — this engine never modifies data.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from ..safety_gate import SafetyGate, ActionCategory, get_default_safety_gate
from ._types import (
    ImpactRiskLevel,
    ImpactField,
    ImpactPreview,
    DBImpactPreview,
    FileImpactPreview,
    EmailImpactPreview,
)
from ._db_preview import preview_db_operation as _preview_db_operation
from ._file_preview import preview_file_operation as _preview_file_operation
from ._email_preview import preview_email as _preview_email
from ._conversions import (
    db_preview_to_impact,
    file_preview_to_impact,
    email_preview_to_impact,
    generic_preview,
)

logger = logging.getLogger(__name__)


class ImpactPreviewEngine:
    """Simulates an action and reports its effects WITHOUT executing it.

    This engine is strictly READ-ONLY — it never modifies data.
    It uses SafetyGate to classify actions for preview routing,
    ensuring the preview respects the same risk taxonomy as
    the execution pipeline.

    Thread-safe: All public methods guarded by RLock.
    """

    def __init__(
        self,
        safety_gate: Optional[SafetyGate] = None,
        db_retry_max: int = 3,
        db_retry_base_delay: float = 0.5,
    ) -> None:
        self._lock = threading.RLock()
        self._safety_gate = safety_gate or get_default_safety_gate()
        self._db_retry_max = db_retry_max
        self._db_retry_base_delay = db_retry_base_delay
        self._preview_count: int = 0

    # ── Public API ────────────────────────────────────────

    def preview_action(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ImpactPreview:
        """Simulate what would happen if the action were executed.

        Routes to the appropriate specialized preview method based on
        action type classification from SafetyGate.

        Args:
            action_type: The type of action to preview (e.g. "database", "file", "email").
            config: The action configuration dict.
            context: Optional context dict.

        Returns:
            An ImpactPreview describing what would happen.
        """
        with self._lock:
            self._preview_count += 1
            context = context or {}

            # Use SafetyGate to classify the action category
            category = self._safety_gate._classify_action(action_type, config)

            # Route to specialized preview based on action type
            action_lower = action_type.lower()

            if action_lower in ("database", "db", "database_operation"):
                db_preview = self.preview_db_operation(config)
                return db_preview_to_impact(action_type, category, db_preview)

            if action_lower in ("file", "file_operation"):
                file_preview = self.preview_file_operation(config)
                return file_preview_to_impact(action_type, category, file_preview)

            if action_lower in ("email", "send_email"):
                email_preview = self.preview_email(config)
                return email_preview_to_impact(action_type, category, email_preview)

            # Generic preview for other action types
            return generic_preview(action_type, config, context, category)

    def preview_db_operation(self, config: Dict[str, Any]) -> DBImpactPreview:
        """Preview a database operation WITHOUT executing it.

        Delegates to the _db_preview module for the actual logic.
        Thread-safe via self._lock.
        """
        with self._lock:
            return _preview_db_operation(
                config,
                db_retry_max=self._db_retry_max,
                db_retry_base_delay=self._db_retry_base_delay,
            )

    def preview_file_operation(self, config: Dict[str, Any]) -> FileImpactPreview:
        """Preview a file operation WITHOUT executing it.

        Delegates to the _file_preview module for the actual logic.
        Thread-safe via self._lock.
        """
        with self._lock:
            return _preview_file_operation(config)

    def preview_email(self, config: Dict[str, Any]) -> EmailImpactPreview:
        """Preview an email operation WITHOUT sending it.

        Delegates to the _email_preview module for the actual logic.
        Thread-safe via self._lock.
        """
        with self._lock:
            return _preview_email(config)

    def compare_scenarios(
        self,
        action_type: str,
        configs: List[Dict[str, Any]],
    ) -> List[ImpactPreview]:
        """A/B comparison of multiple approaches for the same action type.

        Generates an ImpactPreview for each config, allowing the caller
        to compare different approaches before choosing one.

        Args:
            action_type: The type of action to preview.
            configs: List of config dicts, one per scenario.

        Returns:
            A list of ImpactPreview objects, one per config.
        """
        with self._lock:
            results: List[ImpactPreview] = []
            for idx, config in enumerate(configs):
                try:
                    preview = self.preview_action(
                        action_type, config,
                        context={"scenario_index": idx},
                    )
                    preview.metadata["scenario_index"] = idx
                    results.append(preview)
                except Exception as exc:
                    logger.warning(
                        "ImpactPreviewEngine: compare_scenarios failed for config %d: %s",
                        idx, exc,
                    )
                    # Still produce a preview for the failed scenario
                    results.append(ImpactPreview(
                        action_type=action_type,
                        category=ActionCategory.MODERATE,
                        risk_level=ImpactRiskLevel.HIGH,
                        risk_score=0.9,
                        summary=f"Could not preview scenario {idx}: {exc}",
                        warnings=[f"Preview error: {exc}"],
                        metadata={"scenario_index": idx, "error": str(exc)},
                    ))
            return results

    # ── Stats ──────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        with self._lock:
            return {
                "preview_count": self._preview_count,
            }


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_impact_preview_engine: Optional[ImpactPreviewEngine] = None
_impact_preview_lock = threading.Lock()


def get_impact_preview_engine() -> ImpactPreviewEngine:
    """Get or create the global ImpactPreviewEngine instance."""
    global _impact_preview_engine
    with _impact_preview_lock:
        if _impact_preview_engine is None:
            _impact_preview_engine = ImpactPreviewEngine()
        return _impact_preview_engine


def reset_impact_preview_engine() -> None:
    """Reset the global ImpactPreviewEngine (for testing)."""
    global _impact_preview_engine
    with _impact_preview_lock:
        _impact_preview_engine = None


__all__ = [
    "ImpactRiskLevel",
    "ImpactField",
    "ImpactPreview",
    "DBImpactPreview",
    "FileImpactPreview",
    "EmailImpactPreview",
    "ImpactPreviewEngine",
]
