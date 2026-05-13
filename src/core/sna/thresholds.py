"""
Zenic-Agents Asistente - SNA Threshold Engine

Configurable threshold evaluation engine for the SNA system.
Supports per-monitor, per-tenant, and per-Blueprint thresholds
with cooldown logic to prevent alert storms.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .types import (
    AlertSeverity, MonitorResult, ThresholdConfig, ThresholdOperator,
)
from .persistence import SNAPersistence

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  THRESHOLD ENGINE
# ──────────────────────────────────────────────────────────────

class ThresholdEngine:
    """Evaluates monitor results against configurable thresholds.

    Features:
      - Per-monitor, per-tenant, per-Blueprint thresholds
      - Cooldown periods to prevent alert storms
      - Severity escalation based on threshold breach magnitude
      - Persistent storage via SNAPersistence
      - Runtime threshold CRUD operations
    """

    def __init__(self, persistence: Optional[SNAPersistence] = None) -> None:
        self._persistence = persistence or SNAPersistence()
        self._cooldown_tracker: Dict[str, float] = {}  # key → last_alert_time
        self._runtime_thresholds: Dict[str, ThresholdConfig] = {}
        self._stats = {
            "evaluations": 0,
            "breaches": 0,
            "cooldown_blocks": 0,
        }

    # ── Evaluation ─────────────────────────────────────────

    def evaluate(self, result: MonitorResult,
                 tenant_id: str = "") -> Optional[ThresholdConfig]:
        """Evaluate a monitor result against all applicable thresholds.

        Returns the first breached ThresholdConfig, or None if all OK.
        Respects cooldown periods to prevent duplicate alerts.
        """
        self._stats["evaluations"] += 1

        # Get all thresholds for this monitor
        thresholds = self._get_applicable_thresholds(
            result.monitor_id, tenant_id,
        )

        for threshold in thresholds:
            if self._check_breach(result, threshold):
                # Check cooldown
                cooldown_key = f"{threshold.threshold_id}:{tenant_id}"
                last_alert = self._cooldown_tracker.get(cooldown_key, 0)
                if time.time() - last_alert < threshold.cooldown_seconds:
                    self._stats["cooldown_blocks"] += 1
                    logger.debug(
                        "ThresholdEngine: Cooldown active for %s",
                        threshold.threshold_id,
                    )
                    continue

                # Threshold breached and not in cooldown
                self._stats["breaches"] += 1
                self._cooldown_tracker[cooldown_key] = time.time()
                return threshold

        return None

    def _check_breach(self, result: MonitorResult,
                      threshold: ThresholdConfig) -> bool:
        """Check if a monitor result breaches a specific threshold."""
        # Extract the numeric value from the result
        actual_value = self._extract_value(result, threshold.field_name)
        if actual_value is None:
            return False

        try:
            return threshold.evaluate(float(actual_value))
        except (ValueError, TypeError):
            logger.debug(
                "ThresholdEngine: Cannot convert value %r to float for %s",
                actual_value, threshold.field_name,
            )
            return False

    def _extract_value(self, result: MonitorResult,
                       field_name: str) -> Optional[float]:
        """Extract a numeric value from a MonitorResult."""
        # Try result.value first (might be dict or scalar)
        if result.value is not None:
            if isinstance(result.value, dict):
                val = result.value.get(field_name)
                if val is not None:
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        pass
            elif field_name in ("value", "default"):
                try:
                    return float(result.value)
                except (ValueError, TypeError):
                    pass

        # Try metadata
        if field_name in result.metadata:
            try:
                return float(result.metadata[field_name])
            except (ValueError, TypeError):
                pass

        return None

    def _get_applicable_thresholds(
        self, monitor_id: str, tenant_id: str = "",
    ) -> List[ThresholdConfig]:
        """Get all thresholds applicable to a monitor+tenant combination."""
        thresholds: List[ThresholdConfig] = []

        # Runtime thresholds (highest priority)
        for t in self._runtime_thresholds.values():
            if t.monitor_id == monitor_id:
                if not t.tenant_id or t.tenant_id == tenant_id:
                    thresholds.append(t)

        # Persistent thresholds
        if self._persistence:
            try:
                db_thresholds = self._persistence.get_thresholds(
                    monitor_id=monitor_id, tenant_id=tenant_id,
                )
                # Avoid duplicates (runtime takes precedence)
                existing_ids = {t.threshold_id for t in thresholds}
                for t in db_thresholds:
                    if t.threshold_id not in existing_ids:
                        thresholds.append(t)
            except Exception as e:
                logger.debug(
                    "ThresholdEngine: Failed to load persistent thresholds: %s", e,
                )

        return thresholds

    # ── CRUD Operations ────────────────────────────────────

    def add_threshold(self, threshold: ThresholdConfig) -> None:
        """Add or update a threshold configuration.

        Stores in runtime cache and persists to database.
        """
        self._runtime_thresholds[threshold.threshold_id] = threshold
        if self._persistence:
            try:
                self._persistence.save_threshold(threshold)
            except Exception as e:
                logger.warning(
                    "ThresholdEngine: Failed to persist threshold %s: %s",
                    threshold.threshold_id, e,
                )
        logger.info(
            "ThresholdEngine: Added threshold %s for monitor %s "
            "(%s %s %s, severity=%s)",
            threshold.threshold_id, threshold.monitor_id,
            threshold.field_name, threshold.operator.value, threshold.value,
            threshold.severity.value,
        )

    def remove_threshold(self, threshold_id: str) -> bool:
        """Remove a runtime threshold."""
        if threshold_id in self._runtime_thresholds:
            del self._runtime_thresholds[threshold_id]
            return True
        return False

    def get_thresholds(self, monitor_id: str = "",
                       tenant_id: str = "") -> List[ThresholdConfig]:
        """Get all configured thresholds."""
        return self._get_applicable_thresholds(monitor_id, tenant_id)

    # ── Convenience: Create thresholds from monitor_hooks ──

    def load_from_blueprint_hooks(
        self, monitor_hooks: Dict[str, Dict[str, Any]],
        blueprint_name: str = "",
        tenant_id: str = "",
    ) -> int:
        """Load thresholds from Blueprint.monitor_hooks.

        Blueprint monitor_hooks format:
        {
            "low_stock": {
                "thresholds": [
                    {"field": "value", "operator": "gte", "value": 5,
                     "severity": "warning", "cooldown": 300}
                ]
            }
        }

        Returns the number of thresholds loaded.
        """
        loaded = 0
        for monitor_id, hook_config in monitor_hooks.items():
            threshold_list = hook_config.get("thresholds", [])
            for i, th_data in enumerate(threshold_list):
                try:
                    threshold = ThresholdConfig(
                        threshold_id=f"bp_{monitor_id}_{i}",
                        monitor_id=monitor_id,
                        field_name=th_data.get("field", "value"),
                        operator=ThresholdOperator(th_data.get("operator", "gte")),
                        value=float(th_data.get("value", 0)),
                        value_high=float(th_data["value_high"]) if "value_high" in th_data else None,
                        severity=AlertSeverity(th_data.get("severity", "warning")),
                        cooldown_seconds=float(th_data.get("cooldown", 300)),
                        tenant_id=tenant_id,
                        blueprint_name=blueprint_name,
                    )
                    self.add_threshold(threshold)
                    loaded += 1
                except (ValueError, KeyError) as e:
                    logger.warning(
                        "ThresholdEngine: Invalid threshold in monitor_hooks "
                        "for %s[%d]: %s", monitor_id, i, e,
                    )
        return loaded

    # ── Cooldown Management ────────────────────────────────

    def clear_cooldown(self, threshold_id: str, tenant_id: str = "") -> None:
        """Clear cooldown for a specific threshold, allowing immediate re-alert."""
        cooldown_key = f"{threshold_id}:{tenant_id}"
        self._cooldown_tracker.pop(cooldown_key, None)

    def clear_all_cooldowns(self) -> None:
        """Clear all cooldowns."""
        self._cooldown_tracker.clear()

    # ── Statistics ─────────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        """Get threshold engine statistics."""
        return {
            **self._stats,
            "runtime_thresholds": len(self._runtime_thresholds),
            "active_cooldowns": sum(
                1 for t in self._cooldown_tracker.values()
                if time.time() - t < 300  # Count recent cooldowns
            ),
        }
