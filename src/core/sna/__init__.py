"""
Zenic-Agents Asistente - Sistema Nervioso Autónomo (SNA)

Proactive monitoring and autonomous alerting subsystem.
Monitors business and system conditions, evaluates thresholds,
and dispatches notifications/actions through the DAG pipeline
without requiring user requests.

Architecture:
  SNAEngine (facade)
  ├── SNAScheduler (priority-based async scheduler)
  │   └── AlarmManager (Android/Termux wake-up)
  ├── Monitors (lightweight/medium/heavy)
  │   ├── lightweight: stock, invoices, appointments, disk, health
  │   ├── medium: sales trends, CRM, response time, error rate
  │   └── heavy: demand projection, multi-source, capacity planning
  ├── ThresholdEngine (configurable threshold evaluation)
  ├── AlertManager (alert lifecycle + deduplication + routing)
  ├── SNADagBridge (SNA → DAG pipeline integration)
  │   └── ReflexArc (time-critical bypass)
  └── SNAPersistence (SQLite/SQLCipher storage)

Usage:
    from src.core.sna import get_sna_engine

    engine = get_sna_engine()
    engine.load_default_monitors()
    await engine.start()

    # Check status
    stats = engine.detailed_stats

    # Manual check
    result = await engine.check_monitor("low_stock")

    # Stop
    await engine.stop()
"""

from .types import (
    # Enums
    MonitorWeight,
    AlertSeverity,
    AlertStatus,
    ThresholdOperator,
    SchedulerState,
    # Dataclasses
    MonitorResult,
    ThresholdConfig,
    Alert,
    MonitorConfig,
    SNAStats,
    # Constants
    DEFAULT_INTERVALS,
    DEFAULT_CHANNELS,
    MAX_ALERTS_PER_TENANT_PER_HOUR,
)

from .persistence import SNAPersistence

from .scheduler import SNAScheduler, AlarmManager

from .thresholds import ThresholdEngine

from .alert_manager import AlertManager

from .dag_integration import SNADagBridge, ReflexArc

from .sna_engine import SNAEngine, get_sna_engine, reset_sna_engine

from .monitores import (
    MonitorBase,
    register_monitor,
    get_monitor_class,
    get_all_monitor_ids,
    create_monitor,
    # Lightweight
    LowStockMonitor,
    OverdueInvoiceMonitor,
    TomorrowAppointmentMonitor,
    DiskSpaceMonitor,
    SystemHealthMonitor,
    # Medium
    SalesTrendMonitor,
    CRMConversionMonitor,
    ResponseTimeMonitor,
    ErrorRateMonitor,
    # Heavy
    DemandProjectionMonitor,
    MultiSourceAnalysisMonitor,
    CapacityPlanningMonitor,
)

__all__ = [
    # Types
    "MonitorWeight", "AlertSeverity", "AlertStatus",
    "ThresholdOperator", "SchedulerState",
    "MonitorResult", "ThresholdConfig", "Alert", "MonitorConfig", "SNAStats",
    "DEFAULT_INTERVALS", "DEFAULT_CHANNELS", "MAX_ALERTS_PER_TENANT_PER_HOUR",
    # Core
    "SNAPersistence",
    "SNAScheduler", "AlarmManager",
    "ThresholdEngine",
    "AlertManager",
    "SNADagBridge", "ReflexArc",
    "SNAEngine", "get_sna_engine", "reset_sna_engine",
    # Monitors
    "MonitorBase", "register_monitor", "get_monitor_class",
    "get_all_monitor_ids", "create_monitor",
    "LowStockMonitor", "OverdueInvoiceMonitor",
    "TomorrowAppointmentMonitor", "DiskSpaceMonitor",
    "SystemHealthMonitor",
    "SalesTrendMonitor", "CRMConversionMonitor",
    "ResponseTimeMonitor", "ErrorRateMonitor",
    "DemandProjectionMonitor", "MultiSourceAnalysisMonitor",
    "CapacityPlanningMonitor",
]
