"""ResourceGovernor main class combining all mixins."""

import time
import threading

from ._imports import logger
from .monitor import MonitorMixin
from .api import APIMixin
from .model_swap import ModelSwapMixin


class ResourceGovernor(
    MonitorMixin,
    APIMixin,
    ModelSwapMixin,
):
    """
    Governor de recursos que protege el telefono del overheating y OOM.

    Tu Redmi 12R Pro tiene 12+8GB RAM (20GB total con virtual).
    Esto no significa que debamos usarlo todo. El governor mantiene:

    - RAM limit: 4GB max para el engine (deja 16GB para Android)
    - CPU throttle: 70% max (deja 30% para el SO)
    - Thermal: si el proceso lleva >30s a >60% CPU, reduce agresividad
    - GC agresivo: cada 60s o cuando RAM > 3GB
    """

    # Limites conservadores para un telefono
    DEFAULT_RAM_LIMIT_MB = 4096       # 4GB max para el engine
    DEFAULT_GC_THRESHOLD_MB = 3072    # Forzar GC a 3GB
    DEFAULT_CPU_SLEEP_MS = 50         # 50ms sleep entre ops pesadas
    DEFAULT_CPU_SAMPLE_INTERVAL = 5   # Muestrear cada 5s
    THERMAL_SCALE_BACK_THRESHOLD = 30  # Si >30s a alta CPU, reducir

    def __init__(self, ram_limit_mb=None, gc_threshold_mb=None):
        self.ram_limit_mb = ram_limit_mb or self.DEFAULT_RAM_LIMIT_MB
        self.gc_threshold_mb = gc_threshold_mb or self.DEFAULT_GC_THRESHOLD_MB

        self._monitor_thread = None
        self._stop_event = threading.Event()
        self._cpu_usage = 0.0
        self._ram_usage_mb = 0.0
        self._last_cpu_check = time.time()
        self._high_cpu_start = None  # Cuando empezo el pico de CPU
        self._thermal_throttle = 1.0  # 1.0 = normal, 0.5 = reducir a la mitad
        self._gc_count = 0
        self._request_count = 0
        self._request_count_lock = threading.Lock()
        self._model_manager = None  # Ref to ModelManager for model swap

        # Stats
        self.stats = {
            "gc_forced": 0,
            "thermal_throttles": 0,
            "ram_peaks": 0,
            "requests_served": 0,
        }

        logger.info(
            "ResourceGovernor: RAM limit=%dMB, GC threshold=%dMB",
            self.ram_limit_mb, self.gc_threshold_mb
        )
