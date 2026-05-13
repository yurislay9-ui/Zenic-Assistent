"""Singleton functions for ResourceGovernor."""

import threading

from ._imports import logger
from .governor import ResourceGovernor

_governor = None
_governor_lock = threading.Lock()


def get_governor() -> 'ResourceGovernor':
    """Obtiene el singleton del ResourceGovernor (thread-safe with double-checked locking)."""
    global _governor
    if _governor is None:
        with _governor_lock:
            if _governor is None:
                _governor = ResourceGovernor()
    return _governor


def init_governor(ram_limit_mb=None) -> 'ResourceGovernor':
    """Inicializa el governor con configuracion custom (thread-safe)."""
    global _governor
    with _governor_lock:
        _governor = ResourceGovernor(ram_limit_mb=ram_limit_mb)
        _governor.start_monitoring()
    return _governor
