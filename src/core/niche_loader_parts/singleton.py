"""Singleton for NicheLoader."""

import threading

_niche_loader_instance = None
_niche_loader_lock = threading.Lock()


def get_niche_loader():
    """Obtiene la instancia singleton del NicheLoader."""
    global _niche_loader_instance
    if _niche_loader_instance is None:
        with _niche_loader_lock:
            if _niche_loader_instance is None:
                from .loader import NicheLoader
                _niche_loader_instance = NicheLoader()
    return _niche_loader_instance
