"""
ZENIC-AGENTS - Timeout Enforcer v16

Enfuerza timeouts reales usando threading.Event.
Compatible con Android/Termux (no usa signal.alarm).
"""

import threading
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

__all__ = ["TimeoutEnforcer"]


# ============================================================
#  TIMEOUT ENFORCER - Mecanismo de Timeout Real
# ============================================================

class TimeoutEnforcer:
    """
    Enfuerza timeouts reales usando threading.Event.
    Compatible con Android/Termux (no usa signal.alarm).
    """

    def __init__(self, timeout_ms: int = 5000):
        self.timeout_ms = timeout_ms
        self._timed_out = False
        self._event = threading.Event()

    def execute_with_timeout(self, func: Callable[..., Any], *args, **kwargs):
        """
        Ejecuta una funcion con un timeout estricto.

        Returns:
            (result, timed_out) tuple
        """
        self._timed_out = False
        self._event.clear()
        result_container = [None]
        exception_container = [None]

        def worker():
            try:
                result_container[0] = func(*args, **kwargs)
            except Exception as e:
                exception_container[0] = e
            finally:
                self._event.set()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        completed = self._event.wait(timeout=self.timeout_ms / 1000.0)

        if not completed:
            self._timed_out = True
            return None, True

        if exception_container[0]:
            raise exception_container[0]

        return result_container[0], False

    @property
    def timed_out(self) -> bool:
        return self._timed_out
