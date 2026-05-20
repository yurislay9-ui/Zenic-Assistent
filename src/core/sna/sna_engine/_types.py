"""Types and constants for sna_engine."""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from ..types import (
    MonitorWeight, AlertSeverity, AlertStatus, ThresholdOperator,
    SchedulerState, MonitorResult, ThresholdConfig, Alert,
    MonitorConfig, SNAStats,
)
from ..persistence import SNAPersistence
from ..scheduler import SNAScheduler
from ..thresholds import ThresholdEngine
from ..alert_manager import AlertManager
from ..dag_integration import SNADagBridge, ReflexArc
from ..monitores.base import create_monitor, get_all_monitor_ids

logger = logging.getLogger(__name__)

_default_engine: Optional[Any] = None
