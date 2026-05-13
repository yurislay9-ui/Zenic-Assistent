"""
Zenic-Agents Asistente - SNA Monitores Package

Exports all monitor classes and the monitor registry utilities.
Importing this package registers all built-in monitors.
"""

from .base import (
    MonitorBase,
    register_monitor,
    get_monitor_class,
    get_all_monitor_ids,
    create_monitor,
)

# Import monitor modules to trigger @register_monitor decorators
from .lightweight import (
    LowStockMonitor,
    OverdueInvoiceMonitor,
    TomorrowAppointmentMonitor,
    DiskSpaceMonitor,
    SystemHealthMonitor,
)

from .medium import (
    SalesTrendMonitor,
    CRMConversionMonitor,
    ResponseTimeMonitor,
    ErrorRateMonitor,
)

from .heavy import (
    DemandProjectionMonitor,
    MultiSourceAnalysisMonitor,
    CapacityPlanningMonitor,
)

__all__ = [
    # Base
    "MonitorBase",
    "register_monitor",
    "get_monitor_class",
    "get_all_monitor_ids",
    "create_monitor",
    # Lightweight
    "LowStockMonitor",
    "OverdueInvoiceMonitor",
    "TomorrowAppointmentMonitor",
    "DiskSpaceMonitor",
    "SystemHealthMonitor",
    # Medium
    "SalesTrendMonitor",
    "CRMConversionMonitor",
    "ResponseTimeMonitor",
    "ErrorRateMonitor",
    # Heavy
    "DemandProjectionMonitor",
    "MultiSourceAnalysisMonitor",
    "CapacityPlanningMonitor",
]
