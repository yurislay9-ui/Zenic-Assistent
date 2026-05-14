"""
Zenic-Agents Asistente - SNA Alert Manager

Manages alert lifecycle: creation, deduplication, severity routing,
and notification channel selection. Integrates with the ActionDispatcher
for executing alert-driven actions through the DAG pipeline.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from .types import (
    Alert, AlertSeverity, AlertStatus, MonitorResult, MonitorConfig,
    ThresholdConfig, DEFAULT_CHANNELS, MAX_ALERTS_PER_TENANT_PER_HOUR,
)
from .persistence import SNAPersistence

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  ALERT DEDUPLICATION
# ──────────────────────────────────────────────────────────────

class AlertDeduplicator:
    """Prevents duplicate alerts for the same monitor condition.

    Tracks active alerts by (monitor_id, tenant_id) and blocks
    new alerts until the previous one is resolved or expired.
    """

    def __init__(self) -> None:
        self._active_keys: Dict[str, str] = {}  # key → alert_id

    def is_duplicate(self, monitor_id: str, tenant_id: str = "") -> bool:
        """Check if an alert for this monitor+tenant is already active."""
        key = f"{monitor_id}:{tenant_id}"
        return key in self._active_keys

    def register(self, alert: Alert) -> None:
        """Register a new active alert."""
        key = f"{alert.monitor_id}:{alert.tenant_id}"
        self._active_keys[key] = alert.alert_id

    def resolve(self, monitor_id: str, tenant_id: str = "") -> None:
        """Mark an alert as resolved (allows new alerts)."""
        key = f"{monitor_id}:{tenant_id}"
        self._active_keys.pop(key, None)

    def clear_expired(self, active_alerts: List[Alert]) -> None:
        """Remove keys for alerts that are resolved or expired."""
        active_ids = {a.alert_id for a in active_alerts}
        expired_keys = [
            k for k, v in self._active_keys.items()
            if v not in active_ids
        ]
        for k in expired_keys:
            del self._active_keys[k]


# ──────────────────────────────────────────────────────────────
#  ALERT RATE LIMITER
# ──────────────────────────────────────────────────────────────

class AlertRateLimiter:
    """Per-tenant rate limiter to prevent alert spam."""

    def __init__(self, max_per_hour: int = MAX_ALERTS_PER_TENANT_PER_HOUR) -> None:
        self._max_per_hour = max_per_hour
        self._timestamps: Dict[str, List[float]] = {}

    def is_allowed(self, tenant_id: str) -> bool:
        """Check if tenant is within alert rate limit."""
        now = time.time()
        ts_list = self._timestamps.setdefault(tenant_id, [])
        # Clean old entries
        ts_list[:] = [t for t in ts_list if now - t < 3600]
        if len(ts_list) >= self._max_per_hour:
            return False
        ts_list.append(now)
        return True


# ──────────────────────────────────────────────────────────────
#  ALERT MANAGER
# ──────────────────────────────────────────────────────────────

class AlertManager:
    """Central alert manager for the SNA system.

    Responsibilities:
      - Create alerts from monitor results and threshold breaches
      - Deduplicate alerts to prevent spam
      - Route alerts to appropriate notification channels
      - Track alert lifecycle (pending → dispatched → notified → resolved)
      - Persist alerts to SQLite/SQLCipher
      - Generate dispatch_actions for DAG integration
    """

    def __init__(self, persistence: Optional[SNAPersistence] = None) -> None:
        self._persistence = persistence or SNAPersistence()
        self._dedup = AlertDeduplicator()
        self._rate_limiter = AlertRateLimiter()
        self._stats = {
            "created": 0,
            "deduplicated": 0,
            "rate_limited": 0,
            "dispatched": 0,
            "notified": 0,
            "resolved": 0,
        }

    # ── Alert Creation ─────────────────────────────────────

    def create_alert(
        self,
        result: MonitorResult,
        threshold: Optional[ThresholdConfig] = None,
        config: Optional[MonitorConfig] = None,
        tenant_id: str = "",
    ) -> Optional[Alert]:
        """Create an alert from a monitor result.

        Returns None if the alert is deduplicated or rate-limited.
        """
        if not result.triggered:
            return None

        # Deduplication check
        if self._dedup.is_duplicate(result.monitor_id, tenant_id):
            self._stats["deduplicated"] += 1
            logger.debug(
                "AlertManager: Deduplicated alert for %s", result.monitor_id,
            )
            return None

        # Rate limit check
        if not self._rate_limiter.is_allowed(tenant_id):
            self._stats["rate_limited"] += 1
            logger.debug(
                "AlertManager: Rate limited alert for tenant %s", tenant_id,
            )
            return None

        # Determine severity
        severity = result.severity
        if threshold:
            severity = threshold.severity

        # Determine notification channel
        channel = DEFAULT_CHANNELS.get(severity, "log")
        if config and config.notification_channel:
            channel = config.notification_channel

        # Build alert
        alert = Alert(
            monitor_id=result.monitor_id,
            monitor_name=result.monitor_name,
            severity=severity,
            status=AlertStatus.PENDING,
            title=self._build_title(result, threshold),
            message=self._build_message(result, threshold),
            value=result.value,
            threshold=threshold,
            tenant_id=tenant_id,
            channel=channel,
            dispatch_actions=self._build_dispatch_actions(result, config, channel),
            metadata=result.metadata,
        )

        # Persist
        try:
            self._persistence.save_alert(alert)
        except Exception as e:
            logger.warning("AlertManager: Failed to persist alert %s: %s", alert.alert_id, e)

        self._dedup.register(alert)
        self._stats["created"] += 1
        logger.info(
            "AlertManager: Created alert %s [%s] %s: %s",
            alert.alert_id, alert.severity.value, alert.monitor_id, alert.title,
        )
        return alert

    # ── Alert Lifecycle ────────────────────────────────────

    def mark_dispatched(self, alert_id: str) -> None:
        """Mark an alert as dispatched to the DAG pipeline."""
        self._update_status(alert_id, AlertStatus.DISPATCHED)
        self._stats["dispatched"] += 1

    def mark_notified(self, alert_id: str) -> None:
        """Mark an alert as successfully notified."""
        self._update_status(alert_id, AlertStatus.NOTIFIED)
        self._stats["notified"] += 1

    def acknowledge_alert(self, alert_id: str) -> None:
        """Acknowledge an alert (user confirmed awareness)."""
        self._update_status(alert_id, AlertStatus.ACKNOWLEDGED)

    def resolve_alert(self, alert_id: str, monitor_id: str = "",
                      tenant_id: str = "") -> None:
        """Resolve an alert (condition no longer active)."""
        self._update_status(alert_id, AlertStatus.RESOLVED)
        if monitor_id:
            self._dedup.resolve(monitor_id, tenant_id)
        self._stats["resolved"] += 1

    def resolve_auto(self, tenant_id: str = "") -> int:
        """Auto-resolve alerts whose triggering condition is no longer active.

        Returns the number of auto-resolved alerts.
        """
        active = self._get_active_alerts(tenant_id)
        resolved = 0
        now = time.time()
        for alert in active:
            if alert.is_expired:
                self.resolve_alert(alert.alert_id, alert.monitor_id, alert.tenant_id)
                resolved += 1
            elif now - alert.created_at > 86400:  # Auto-resolve after 24h
                self.resolve_alert(alert.alert_id, alert.monitor_id, alert.tenant_id)
                resolved += 1
        return resolved

    # ── Query ──────────────────────────────────────────────

    def get_active_alerts(self, tenant_id: str = "") -> List[Alert]:
        """Get all active (non-resolved, non-expired) alerts."""
        return self._get_active_alerts(tenant_id)

    def get_pending_alerts(self, tenant_id: str = "") -> List[Alert]:
        """Get alerts awaiting dispatch."""
        alerts = self._get_active_alerts(tenant_id)
        return [a for a in alerts if a.status == AlertStatus.PENDING]

    # ── Private Methods ────────────────────────────────────

    def _update_status(self, alert_id: str, status: AlertStatus) -> None:
        """Update alert status in persistence."""
        try:
            self._persistence.update_alert_status(alert_id, status)
        except Exception as e:
            logger.warning(
                "AlertManager: Failed to update alert %s status: %s", alert_id, e,
            )

    def _get_active_alerts(self, tenant_id: str = "") -> List[Alert]:
        """Get active alerts from persistence."""
        try:
            return self._persistence.get_active_alerts(tenant_id)
        except Exception as e:
            logger.warning("AlertManager: Failed to get active alerts: %s", e)
            return []

    def _build_title(self, result: MonitorResult,
                     threshold: Optional[ThresholdConfig]) -> str:
        """Build a concise alert title."""
        if threshold:
            return f"{result.monitor_name}: {threshold.field_name} {threshold.operator.value} {threshold.value}"
        return f"{result.monitor_name}: Condicion detectada"

    def _build_message(self, result: MonitorResult,
                       threshold: Optional[ThresholdConfig]) -> str:
        """Build a detailed alert message."""
        parts = [result.detail]
        if result.value is not None:
            parts.append(f"Valor: {result.value}")
        if threshold:
            parts.append(f"Umbral: {threshold.field_name} {threshold.operator.value} {threshold.value}")
        return " | ".join(parts)

    def _build_dispatch_actions(
        self,
        result: MonitorResult,
        config: Optional[MonitorConfig],
        channel: str,
    ) -> List[Dict[str, Any]]:
        """Build dispatch actions for the DAG pipeline.

        The primary action is a notification, but additional actions
        can be configured per monitor via Blueprint monitor_hooks.
        """
        actions: List[Dict[str, Any]] = []

        # Primary action: Send notification
        notification_config: Dict[str, Any] = {
            "channel": channel,
            "message": result.detail,
            "subject": f"[SNA] {result.monitor_name}",
        }
        if result.metadata.get("low_items"):
            notification_config["html"] = self._format_items_html(result)
        actions.append({
            "type": "notification",
            "config": notification_config,
        })

        # Additional actions from monitor config params
        if config and config.params.get("dispatch_actions"):
            for action in config.params["dispatch_actions"]:
                actions.append(action)

        return actions

    def _format_items_html(self, result: MonitorResult) -> str:
        """Format a simple HTML list for notification content."""
        items = result.metadata.get("low_items", [])
        if not items:
            return ""
        rows = "".join(
            f"<tr><td>{i.get('name', '?')}</td><td>{i.get('quantity', '?')}</td></tr>"
            for i in items[:10]
        )
        return f"<table><tr><th>Producto</th><th>Cantidad</th></tr>{rows}</table>"

    @property
    def stats(self) -> Dict[str, Any]:
        """Get alert manager statistics."""
        return {
            **self._stats,
            "active_alerts": len(self.get_active_alerts()),
            "pending_alerts": len(self.get_pending_alerts()),
        }
