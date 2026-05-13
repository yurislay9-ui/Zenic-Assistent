"""Shared imports, PowerMode enum, and HardwareState dataclass for low_power_parts."""

import os
import time
import logging
from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger(__name__)


class PowerMode(Enum):
    """Modos de energia del sistema."""
    NORMAL = "normal"           # Paralelo completo
    CONSERVATIVE = "conservative"  # Secuencial en Capa 4
    EMERGENCY = "emergency"     # Secuencial total, minimo recurso


@dataclass
class HardwareState:
    """Estado del hardware en un momento dado."""
    cpu_usage: float = 0.0       # 0.0 - 1.0
    ram_usage_mb: float = 0.0
    ram_limit_mb: float = 4096
    temperature_c: float = 45.0  # Estimada
    battery_level: float = 100.0  # 0-100%
    battery_charging: bool = True
    thermal_throttle: float = 1.0  # 1.0 = normal, 0.5 = reducido

    @property
    def ram_pct(self) -> float:
        return (self.ram_usage_mb / self.ram_limit_mb * 100) if self.ram_limit_mb > 0 else 0
