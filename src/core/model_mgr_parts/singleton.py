"""Singleton functions for ModelManager."""

import threading

from ._imports import IDLE_TIMEOUT_S, RAM_BUDGET_MB, ENABLE_LAZY_LOAD

_manager = None
_singleton_lock = threading.Lock()


def get_model_manager():
    """Obtiene el singleton del ModelManager."""
    global _manager
    if _manager is None:
        with _singleton_lock:
            if _manager is None:
                from .manager import ModelManager
                _manager = ModelManager()
    return _manager


def init_model_manager(lazy_load: bool = True, idle_timeout_s: int = None,
                       ram_budget_mb: int = None):
    """Inicializa el ModelManager con configuracion custom."""
    global _manager
    from .manager import ModelManager
    _manager = ModelManager(
        lazy_load=lazy_load,
        idle_timeout_s=idle_timeout_s,
        ram_budget_mb=ram_budget_mb,
    )
    _manager.start_auto_unload_monitor()
    return _manager
