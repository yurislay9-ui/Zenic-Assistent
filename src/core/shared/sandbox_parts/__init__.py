"""
sandbox_parts — modularized Sandbox Isolation.

Public API re-exported for backward compatibility.
"""

import threading

from ._workspace import SandboxWorkspace
from ._manager import SandboxIsolationManager
from ._builtins import create_sandbox_builtins, create_sandbox_globals

__all__ = [
    "SandboxWorkspace", "SandboxIsolationManager",
    "get_isolation_manager", "shutdown_isolation",
    "create_sandbox_builtins", "create_sandbox_globals",
]


# ============================================================
#  INSTANCIA GLOBAL DEL MANAGER (Singleton)
# ============================================================

_isolation_manager = None
_manager_lock = threading.Lock()


def get_isolation_manager() -> SandboxIsolationManager:
    """
    Obtiene la instancia singleton del SandboxIsolationManager.
    Thread-safe: se crea una sola instancia compartida.
    """
    global _isolation_manager
    if _isolation_manager is None:
        with _manager_lock:
            if _isolation_manager is None:
                _isolation_manager = SandboxIsolationManager()
    return _isolation_manager


def shutdown_isolation():
    """Detiene el sistema de aislamiento y limpia todos los workspaces."""
    global _isolation_manager
    if _isolation_manager is not None:
        _isolation_manager.shutdown()
        _isolation_manager = None
