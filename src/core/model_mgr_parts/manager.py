"""ModelManager main class combining all mixins."""

import time
import threading

from ._imports import (
    logger, IDLE_TIMEOUT_S, RAM_BUDGET_MB, ENABLE_LAZY_LOAD,
    ENABLE_AUTO_UNLOAD,
)
from .semantic_access import SemanticAccessMixin
from .ai_access import AIAccessMixin
from .unload import UnloadMixin
from .monitor import AutoUnloadMixin
from .ram_mgmt import RAMMixin
from .status import StatusMixin


class ModelManager(
    SemanticAccessMixin,
    AIAccessMixin,
    UnloadMixin,
    AutoUnloadMixin,
    RAMMixin,
    StatusMixin,
):
    """
    Gestor hibrido de modelos AI para maximizar rendimiento en movil.

    Estrategia: Lazy Load + Auto-Unload + RAM Budget
    - Los modelos se cargan SOLO cuando se necesitan (lazy)
    - Los modelos se DESCARGAN tras N minutos sin uso (auto-unload)
    - Si la RAM supera el presupuesto, se descarga el modelo menos usado

    Esto reduce el consumo de RAM de ~730MB permanente a ~50MB idle,
    protegiendo el telefono del sobrecalentamiento y desgaste.
    """

    def __init__(self, lazy_load: bool = None, idle_timeout_s: int = None,
                 ram_budget_mb: int = None):
        self._lazy_load = lazy_load if lazy_load is not None else ENABLE_LAZY_LOAD
        self._idle_timeout_s = idle_timeout_s if idle_timeout_s is not None else IDLE_TIMEOUT_S
        self._ram_budget_mb = ram_budget_mb if ram_budget_mb is not None else RAM_BUDGET_MB

        # Model instances (lazy-created)
        self._semantic_engine = None
        self._mini_ai_engine = None

        # Track last access time for auto-unload
        self._semantic_last_access = 0.0
        self._ai_last_access = 0.0

        # Lock for thread-safe model loading/unloading
        self._lock = threading.RLock()

        # Background monitor for auto-unload
        self._monitor_thread = None
        self._stop_event = threading.Event()
        self._monitor_interval = 30  # Check every 30 seconds

        # Stats
        self._stats = {
            "semantic_loads": 0,
            "semantic_unloads": 0,
            "ai_loads": 0,
            "ai_unloads": 0,
            "auto_unloads": 0,
            "ram_budget_exceeded": 0,
        }

        logger.info(
            f"ModelManager: lazy_load={self._lazy_load}, "
            f"idle_timeout={self._idle_timeout_s}s, "
            f"ram_budget={self._ram_budget_mb}MB, "
            f"auto_unload={ENABLE_AUTO_UNLOAD}"
        )
