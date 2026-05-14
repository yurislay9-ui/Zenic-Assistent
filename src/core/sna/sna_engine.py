"""
Zenic-Agents Asistente - SNA Engine

Main orchestrator for the Sistema Nervioso Autónomo.
Coordinates the Scheduler, Monitors, ThresholdEngine,
AlertManager, and DAG Bridge into a unified subsystem.

This is the primary entry point for SNA functionality.
Start the SNA engine at application startup to enable
proactive monitoring and autonomous alerting.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .types import (
    Alert, AlertSeverity, MonitorConfig, MonitorResult, MonitorWeight,
    SchedulerState, SNAStats, DEFAULT_INTERVALS,
)
from .persistence import SNAPersistence
from .scheduler import SNAScheduler
from .thresholds import ThresholdEngine
from .alert_manager import AlertManager
from .dag_integration import SNADagBridge, ReflexArc
from .monitores.base import create_monitor, get_all_monitor_ids

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  SNA ENGINE
# ──────────────────────────────────────────────────────────────

class SNAEngine:
    """Main engine for the Sistema Nervioso Autónomo.

    Usage:
        engine = SNAEngine()
        engine.load_default_monitors()
        await engine.start()

    The engine runs as a background async task, periodically
    checking monitors and dispatching alerts through the DAG pipeline.
    """

    def __init__(
        self,
        persistence: Optional[SNAPersistence] = None,
        alert_manager: Optional[AlertManager] = None,
        threshold_engine: Optional[ThresholdEngine] = None,
        scheduler: Optional[SNAScheduler] = None,
        dag_bridge: Optional[SNADagBridge] = None,
    ) -> None:
        self._persistence = persistence or SNAPersistence()
        self._alert_mgr = alert_manager or AlertManager(self._persistence)
        self._threshold_engine = threshold_engine or ThresholdEngine(self._persistence)
        self._scheduler = scheduler or SNAScheduler()
        self._dag_bridge = dag_bridge or SNADagBridge(self._alert_mgr)

        # Wire scheduler callback
        self._scheduler.set_check_callback(self._run_monitor_check)

        # Ensure persistence schema
        try:
            self._persistence.ensure_schema()
        except Exception as e:
            logger.warning("SNAEngine: Schema init failed: %s", e)

        # Register default reflex arcs
        self._dag_bridge.register_default_reflex_arcs()

        self._start_time: float = 0.0
        self._total_checks: int = 0
        self._total_triggered: int = 0
        self._background_tasks: set = set()

    # ── Lifecycle ──────────────────────────────────────────

    async def start(self) -> None:
        """Start the SNA engine (scheduler + all monitors)."""
        logger.info("SNAEngine: Starting Sistema Nervioso Autónomo...")
        self._start_time = time.time()

        # Load persisted monitor configs
        self._load_persisted_configs()

        # Start scheduler
        await self._scheduler.start()
        logger.info(
            "SNAEngine: Started with %d monitors",
            len(self._scheduler.get_monitors()),
        )

    async def stop(self) -> None:
        """Stop the SNA engine gracefully."""
        logger.info("SNAEngine: Stopping...")
        await self._scheduler.stop()
        self._persistence.ensure_schema()
        logger.info("SNAEngine: Stopped")

    async def pause(self) -> None:
        """Pause monitoring (scheduler keeps state)."""
        await self._scheduler.pause()

    async def resume(self) -> None:
        """Resume monitoring."""
        await self._scheduler.resume()

    # ── Monitor Management ─────────────────────────────────

    def load_default_monitors(self, tenant_id: str = "",
                              blueprint_name: str = "") -> int:
        """Load all built-in monitors with default configurations.

        Returns the number of monitors loaded.
        """
        loaded = 0
        for monitor_id in get_all_monitor_ids():
            monitor = create_monitor(monitor_id)
            if monitor is None:
                continue
            config = monitor.to_config(tenant_id=tenant_id, blueprint_name=blueprint_name)
            self._scheduler.add_monitor(config)
            # Persist config
            try:
                self._persistence.save_monitor_config(config)
            except Exception:
                pass
            loaded += 1
        logger.info("SNAEngine: Loaded %d default monitors", loaded)
        return loaded

    def add_monitor(self, config: MonitorConfig) -> None:
        """Add a custom monitor configuration."""
        self._scheduler.add_monitor(config)
        try:
            self._persistence.save_monitor_config(config)
        except Exception as e:
            logger.warning("SNAEngine: Failed to persist monitor config: %s", e)

    def remove_monitor(self, monitor_id: str) -> None:
        """Remove a monitor by ID."""
        self._scheduler.remove_monitor(monitor_id)

    def get_monitors(self) -> Dict[str, MonitorConfig]:
        """Get all active monitor configurations."""
        return self._scheduler.get_monitors()

    # ── Threshold Management ───────────────────────────────

    def add_threshold(self, threshold_config: Any) -> None:
        """Add a threshold configuration."""
        from .types import ThresholdConfig
        if isinstance(threshold_config, dict):
            threshold_config = ThresholdConfig(**threshold_config)
        self._threshold_engine.add_threshold(threshold_config)

    def load_blueprint_thresholds(
        self, monitor_hooks: Dict[str, Dict[str, Any]],
        blueprint_name: str = "", tenant_id: str = "",
    ) -> int:
        """Load thresholds from a Blueprint's monitor_hooks."""
        return self._threshold_engine.load_from_blueprint_hooks(
            monitor_hooks, blueprint_name, tenant_id,
        )

    # ── DAG Integration ────────────────────────────────────

    def set_dispatcher(self, dispatcher: Any) -> None:
        """Set the ActionDispatcher for full-pipeline dispatching."""
        self._dag_bridge.set_dispatcher(dispatcher)

    def register_reflex_arc(self, monitor_id: str, action_type: str,
                            action_config: Dict[str, Any],
                            max_per_hour: int = 5) -> None:
        """Register a reflex arc for time-critical responses."""
        self._dag_bridge.register_reflex_arc(ReflexArc(
            monitor_id=monitor_id,
            action_type=action_type,
            action_config=action_config,
            max_per_hour=max_per_hour,
        ))

    # ── Manual Check (API/CLI) ─────────────────────────────

    async def check_monitor(self, monitor_id: str,
                            tenant_id: str = "") -> Optional[MonitorResult]:
        """Manually trigger a monitor check.

        Useful for testing and CLI inspection.
        """
        monitor = create_monitor(monitor_id)
        if monitor is None:
            return None
        config = self._scheduler.get_monitors().get(monitor_id)
        params = config.params if config else {}
        result = await monitor.check(params, tenant_id)
        self._process_result(result, tenant_id, config)
        return result

    async def check_all(self, tenant_id: str = "") -> List[MonitorResult]:
        """Run all active monitors once (regardless of schedule)."""
        results: List[MonitorResult] = []
        for monitor_id in get_all_monitor_ids():
            result = await self.check_monitor(monitor_id, tenant_id)
            if result is not None:
                results.append(result)
        return results

    # ── Alert Management ───────────────────────────────────

    def get_active_alerts(self, tenant_id: str = "") -> List[Alert]:
        """Get all active (non-resolved) alerts."""
        return self._alert_mgr.get_active_alerts(tenant_id)

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        self._alert_mgr.acknowledge_alert(alert_id)
        return True

    def resolve_alert(self, alert_id: str, monitor_id: str = "",
                      tenant_id: str = "") -> bool:
        """Resolve an alert."""
        self._alert_mgr.resolve_alert(alert_id, monitor_id, tenant_id)
        return True

    # ── KPI-Driven Scheduling (Phase D1) ──────────────────

    def add_kpi_driven_monitor(
        self,
        objective_id: str,
        metric_name: str,
        check_interval_seconds: int = 300,
        tenant_id: str = "",
    ) -> Optional[str]:
        """Add a monitor that checks KPI progress for an objective.
        
        Phase D1: Integration with AutopilotEngine.
        Creates a periodic check that measures KPI and feeds
        results back to the autopilot feedback loop.
        """
        from .types import MonitorConfig
        monitor_id = f"kpi_{objective_id}_{metric_name}"
        config = MonitorConfig(
            monitor_id=monitor_id,
            monitor_name=f"KPI: {metric_name} (obj:{objective_id[:8]})",
            interval_seconds=check_interval_seconds,
            enabled=True,
            tenant_id=tenant_id,
            blueprint_name="",
            params={
                "objective_id": objective_id,
                "metric_name": metric_name,
                "kpi_driven": True,
            },
        )
        self.add_monitor(config)
        logger.info(
            "SNAEngine: Added KPI-driven monitor %s for objective %s",
            monitor_id, objective_id,
        )
        return monitor_id

    def remove_kpi_driven_monitor(self, objective_id: str, metric_name: str) -> bool:
        """Remove a KPI-driven monitor."""
        monitor_id = f"kpi_{objective_id}_{metric_name}"
        self.remove_monitor(monitor_id)
        return True

    # ── Core Check Callback ────────────────────────────────

    async def _run_monitor_check(self, config: MonitorConfig) -> None:
        """Scheduler callback: execute a single monitor check."""
        monitor = create_monitor(config.monitor_id)
        if monitor is None:
            logger.warning(
                "SNAEngine: Monitor %s not found, removing from schedule",
                config.monitor_id,
            )
            self._scheduler.remove_monitor(config.monitor_id)
            return

        try:
            result = await monitor.check(config.params, config.tenant_id)
            self._total_checks += 1
            if result.triggered:
                self._total_triggered += 1

            self._process_result(result, config.tenant_id, config)

            # Record check in history
            try:
                self._persistence.record_check(
                    monitor_id=result.monitor_id,
                    triggered=result.triggered,
                    value=result.value,
                    detail=result.detail,
                    duration_ms=result.duration_ms,
                    tenant_id=config.tenant_id,
                )
            except Exception:
                pass

        except Exception as e:
            logger.error(
                "SNAEngine: Monitor %s check failed: %s",
                config.monitor_id, e,
            )

    def _process_result(
        self,
        result: MonitorResult,
        tenant_id: str,
        config: Optional[MonitorConfig] = None,
    ) -> None:
        """Process a monitor result: evaluate thresholds and dispatch alerts.

        Alerts trigger when: (1) monitor's built-in condition detects anomaly,
        or (2) a configured threshold is breached even if monitor didn't trigger.
        """
        threshold = self._threshold_engine.evaluate(result, tenant_id)
        if not (result.triggered or threshold is not None):
            return

        # Override severity if threshold breached but monitor not triggered
        if threshold and not result.triggered:
            result = MonitorResult(
                monitor_id=result.monitor_id, monitor_name=result.monitor_name,
                triggered=True, value=result.value,
                detail=f"[THRESHOLD] {result.detail}", weight=result.weight,
                severity=threshold.severity, metadata=result.metadata,
                duration_ms=result.duration_ms,
            )

        alert = self._alert_mgr.create_alert(
            result=result, threshold=threshold,
            config=config, tenant_id=tenant_id,
        )
        if alert is None:
            return

        if result.severity == AlertSeverity.CRITICAL:
            task = asyncio.create_task(self._dispatch_reflex_and_alert(result, alert))
        else:
            task = asyncio.create_task(self._dag_bridge.dispatch_alert(alert))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _dispatch_reflex_and_alert(
        self, result: MonitorResult, alert: Alert,
    ) -> None:
        """Dispatch reflex arcs and then the full alert."""
        # First: reflex arcs for immediate response
        await self._dag_bridge.check_reflex_arcs(result)
        # Then: full pipeline dispatch
        await self._dag_bridge.dispatch_alert(alert)

    # ── Internal Helpers ───────────────────────────────────

    def _load_persisted_configs(self) -> None:
        """Load monitor configurations from persistence."""
        try:
            configs = self._persistence.get_monitor_configs()
            for config in configs:
                if config.enabled:
                    self._scheduler.add_monitor(config)
            logger.info(
                "SNAEngine: Loaded %d persisted monitor configs", len(configs),
            )
        except Exception as e:
            logger.debug("SNAEngine: No persisted configs: %s", e)

    # ── Statistics ─────────────────────────────────────────

    @property
    def stats(self) -> SNAStats:
        """Get comprehensive SNA statistics."""
        uptime = (time.time() - self._start_time) if self._start_time else 0
        sched_stats = self._scheduler.stats
        return SNAStats(
            total_checks=self._total_checks,
            total_triggered=self._total_triggered,
            total_alerts=self._alert_mgr.stats.get("created", 0),
            total_dispatched=self._alert_mgr.stats.get("dispatched", 0),
            total_notified=self._alert_mgr.stats.get("notified", 0),
            active_monitors=sched_stats.get("active_monitors", 0),
            active_alerts=self._alert_mgr.stats.get("active_alerts", 0),
            scheduler_state=SchedulerState(sched_stats.get("state", "stopped")),
            last_check_time=time.time(),
            scheduler_uptime_seconds=uptime,
        )

    @property
    def detailed_stats(self) -> Dict[str, Any]:
        """Get detailed statistics from all SNA components."""
        return {
            "engine": {
                "total_checks": self._total_checks,
                "total_triggered": self._total_triggered,
                "uptime_seconds": (time.time() - self._start_time) if self._start_time else 0,
            },
            "scheduler": self._scheduler.stats,
            "threshold_engine": self._threshold_engine.stats,
            "alert_manager": self._alert_mgr.stats,
            "dag_bridge": self._dag_bridge.stats,
        }


# ──────────────────────────────────────────────────────────────
#  GLOBAL INSTANCE
# ──────────────────────────────────────────────────────────────

_default_engine: Optional[SNAEngine] = None


def get_sna_engine() -> SNAEngine:
    """Get or create the global SNAEngine instance."""
    global _default_engine
    if _default_engine is None:
        _default_engine = SNAEngine()
    return _default_engine


def reset_sna_engine() -> None:
    """Reset the global SNAEngine (for testing)."""
    global _default_engine
    _default_engine = None
