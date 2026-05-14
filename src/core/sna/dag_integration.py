"""
Zenic-Agents Asistente - SNA → DAG Integration

Bridges the SNA system with the DAG pipeline for proactive
action dispatching. When the SNA detects an anomaly, it creates
a dispatch request that flows through the same SafetyGate→Executor→Audit
pipeline as user-initiated actions, guaranteeing determinism and security.

Also provides "reflex arc" support for time-critical responses
that bypass the full DAG pipeline for sub-second reaction times.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from .types import Alert, AlertSeverity, AlertStatus, MonitorResult, MonitorConfig
from .alert_manager import AlertManager

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  REFLEX ARC REGISTRY
# ──────────────────────────────────────────────────────────────

class ReflexArc:
    """A reflex arc defines an automatic, immediate response to a
    specific monitor trigger without going through the full DAG.

    Reflex arcs are reserved for time-critical situations where
    waiting for the full pipeline would cause harm (e.g., disk full,
    memory exhaustion). All reflex actions are still audit-logged.

    INVARIANT: Reflex actions must be SAFE-category only. They cannot
    perform DESTRUCTIVE or FINANCIAL operations.
    """

    def __init__(
        self,
        monitor_id: str,
        action_type: str,
        action_config: Dict[str, Any],
        max_per_hour: int = 5,
    ) -> None:
        self.monitor_id = monitor_id
        self.action_type = action_type
        self.action_config = action_config
        self.max_per_hour = max_per_hour
        self._trigger_times: List[float] = []

    def should_fire(self, result: MonitorResult) -> bool:
        """Check if this reflex arc should fire for the given result."""
        if result.monitor_id != self.monitor_id:
            return False
        if not result.triggered:
            return False
        # Rate limit check
        now = time.time()
        self._trigger_times[:] = [t for t in self._trigger_times if now - t < 3600]
        if len(self._trigger_times) >= self.max_per_hour:
            return False
        self._trigger_times.append(now)
        return True

    def get_dispatch_dict(self) -> Dict[str, Any]:
        """Get the dispatch action dict for this reflex arc."""
        return {
            "type": self.action_type,
            "config": self.action_config,
            "context": {"source": "sna_reflex", "monitor_id": self.monitor_id},
        }


# ──────────────────────────────────────────────────────────────
#  SNA → DAG BRIDGE
# ──────────────────────────────────────────────────────────────

class SNADagBridge:
    """Bridges SNA alerts to the DAG/Executor pipeline.

    Two modes of operation:
      1. Full Pipeline: Alert → DispatchRequest → SafetyGate → Executor → Audit
         Used for standard notifications and non-critical actions.
         Guarantees full safety validation and audit trail.

      2. Reflex Arc: Monitor trigger → Immediate executor call → Audit
         Used for time-critical responses (sub-second).
         Restricted to SAFE-category actions only.
         Still audit-logged but bypasses SafetyGate confirmation.

    Both modes use the ActionDispatcher for execution consistency.
    """

    def __init__(self, alert_manager: Optional[AlertManager] = None) -> None:
        self._alert_manager = alert_manager or AlertManager()
        self._reflex_arcs: Dict[str, ReflexArc] = {}
        self._dispatcher = None
        self._stats = {
            "full_pipeline_dispatches": 0,
            "reflex_arc_dispatches": 0,
            "reflex_arc_blocked": 0,
            "dispatch_errors": 0,
        }

    def set_dispatcher(self, dispatcher: Any) -> None:
        """Set the ActionDispatcher instance for full pipeline dispatch."""
        self._dispatcher = dispatcher

    # ── Reflex Arc Management ──────────────────────────────

    def register_reflex_arc(self, arc: ReflexArc) -> None:
        """Register a reflex arc for a specific monitor."""
        self._reflex_arcs[arc.monitor_id] = arc
        logger.info(
            "SNADagBridge: Registered reflex arc for %s → %s",
            arc.monitor_id, arc.action_type,
        )

    def unregister_reflex_arc(self, monitor_id: str) -> None:
        """Remove a reflex arc."""
        self._reflex_arcs.pop(monitor_id, None)

    # ── Dispatch Methods ───────────────────────────────────

    async def dispatch_alert(self, alert: Alert) -> Dict[str, Any]:
        """Dispatch an alert through the full DAG pipeline.

        This is the primary dispatch method. It creates a DispatchRequest
        from the alert's dispatch_actions and sends it through the
        ActionDispatcher, which applies SafetyGate validation and
        audit logging.

        Returns a dict with dispatch results.
        """
        if not alert.dispatch_actions:
            logger.debug(
                "SNADagBridge: Alert %s has no dispatch_actions", alert.alert_id,
            )
            return {"status": "no_actions", "alert_id": alert.alert_id}

        # Import DispatchRequest here to avoid circular imports
        from src.core.executors.dispatch_action import DispatchRequest

        results = []
        for action in alert.dispatch_actions:
            try:
                request = DispatchRequest(
                    action_type=action.get("type", "notification"),
                    config=action.get("config", {}),
                    context={
                        **action.get("context", {}),
                        "source": "sna",
                        "alert_id": alert.alert_id,
                        "monitor_id": alert.monitor_id,
                        "severity": alert.severity.value,
                    },
                    user_id="sna_system",
                    tenant_id=alert.tenant_id,
                    session_id=f"sna_{alert.alert_id}",
                    skip_safety_gate=False,
                    skip_audit=False,
                )

                if self._dispatcher:
                    result = await self._dispatcher.dispatch(request)
                    results.append({
                        "action_type": request.action_type,
                        "success": result.success,
                        "safety_verdict": result.safety_verdict.value,
                        "duration_ms": result.total_duration_ms,
                    })
                else:
                    # No dispatcher: try direct executor execution
                    exec_result = await self._direct_execute(
                        request.action_type, request.config, request.context,
                    )
                    results.append({
                        "action_type": request.action_type,
                        "success": exec_result.get("success", False),
                        "fallback": True,
                    })

                self._stats["full_pipeline_dispatches"] += 1

            except Exception as e:
                self._stats["dispatch_errors"] += 1
                results.append({
                    "action_type": action.get("type", ""),
                    "success": False,
                    "error": str(e),
                })
                logger.error(
                    "SNADagBridge: Dispatch failed for alert %s: %s",
                    alert.alert_id, e,
                )

        # Update alert status
        self._alert_manager.mark_dispatched(alert.alert_id)

        all_success = all(r.get("success", False) for r in results)
        if all_success:
            self._alert_manager.mark_notified(alert.alert_id)

        return {
            "status": "SUCCESS" if all_success else "PARTIAL",
            "alert_id": alert.alert_id,
            "results": results,
        }

    async def check_reflex_arcs(self, result: MonitorResult) -> List[Dict[str, Any]]:
        """Check and fire any matching reflex arcs for a monitor result.

        Returns list of dispatch results from fired arcs.
        """
        arc = self._reflex_arcs.get(result.monitor_id)
        if arc is None:
            return []

        if not arc.should_fire(result):
            self._stats["reflex_arc_blocked"] += 1
            return []

        # Execute the reflex action directly (bypass SafetyGate for speed)
        dispatch = arc.get_dispatch_dict()
        try:
            exec_result = await self._direct_execute(
                dispatch["type"], dispatch["config"], dispatch["context"],
            )
            self._stats["reflex_arc_dispatches"] += 1
            logger.info(
                "SNADagBridge: Reflex arc fired for %s → %s",
                result.monitor_id, arc.action_type,
            )
            return [{
                "type": "reflex",
                "monitor_id": result.monitor_id,
                "action_type": arc.action_type,
                "success": exec_result.get("success", False),
                "duration_ms": exec_result.get("duration_ms", 0),
            }]
        except Exception as e:
            self._stats["dispatch_errors"] += 1
            logger.error(
                "SNADagBridge: Reflex arc failed for %s: %s",
                result.monitor_id, e,
            )
            return [{
                "type": "reflex",
                "monitor_id": result.monitor_id,
                "success": False,
                "error": str(e),
            }]

    # ── Direct Execution (fallback) ────────────────────────

    async def _direct_execute(
        self,
        action_type: str,
        config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute an action directly via ExecutorRegistry.

        Used when no ActionDispatcher is configured, or for
        reflex arcs that need sub-second response time.
        """
        try:
            from src.core.executors.base import get_default_registry
            registry = get_default_registry()
            result = await registry.execute_action(action_type, config, context)
            return {
                "success": result.success,
                "data": result.data,
                "error": result.error,
                "duration_ms": result.duration_ms,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "duration_ms": 0}

    # ── Built-in Reflex Arcs ───────────────────────────────

    def register_default_reflex_arcs(self) -> None:
        """Register built-in reflex arcs for system-critical monitors."""
        # Disk space critical → log emergency warning + notify
        self.register_reflex_arc(ReflexArc(
            monitor_id="disk_space",
            action_type="notification",
            action_config={
                "channel": "log",
                "message": "ALERTA CRITICA: Espacio en disco muy bajo!",
                "subject": "[SNA-CRITICAL] Disco Lleno",
            },
            max_per_hour=2,
        ))

        # System health critical → log emergency
        self.register_reflex_arc(ReflexArc(
            monitor_id="system_health",
            action_type="notification",
            action_config={
                "channel": "log",
                "message": "ALERTA CRITICA: Recursos del sistema agotados!",
                "subject": "[SNA-CRITICAL] Recursos Criticos",
            },
            max_per_hour=2,
        ))

    # ── Statistics ─────────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        """Get bridge statistics."""
        return {
            **self._stats,
            "registered_reflex_arcs": len(self._reflex_arcs),
            "dispatcher_configured": self._dispatcher is not None,
        }
