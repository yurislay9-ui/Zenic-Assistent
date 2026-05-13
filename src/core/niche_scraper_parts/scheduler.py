"""
NicheCronScheduler: Background scheduler for periodic auto-updates.
"""

import time
import threading
import logging
from typing import Dict, Any, Optional

from ._imports import logger


class NicheCronScheduler:
    """
    Scheduler de fondo que ejecuta auto-actualizaciones periódicamente.

    Ejecuta el NicheAutoUpdater en intervalos configurables:
    - Intervalo por defecto: 24 horas
    - Mínimo: 1 hora (para no abusar de la API de GitHub)
    - Thread daemon: no bloquea el shutdown del servidor
    """

    DEFAULT_INTERVAL_HOURS = 24
    MIN_INTERVAL_HOURS = 1

    def __init__(self, auto_updater, interval_hours: float = 0):
        self._updater = auto_updater
        self._interval = max(interval_hours or self.DEFAULT_INTERVAL_HOURS, self.MIN_INTERVAL_HOURS)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_run = 0.0
        self._run_count = 0
        self._last_result: Dict[str, Any] = {}

    def start(self):
        """Inicia el scheduler en background."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"NicheCronScheduler: Started with interval={self._interval}h")

    def stop(self):
        """Detiene el scheduler."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("NicheCronScheduler: Stopped")

    def _run_loop(self):
        """Loop principal del scheduler."""
        # Wait initial delay (1 hour after start)
        initial_delay = min(self._interval * 3600, 3600)
        if self._stop_event.wait(timeout=initial_delay):
            return

        while not self._stop_event.is_set():
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                try:
                    self._last_result = loop.run_until_complete(
                        self._updater.auto_update()
                    )
                finally:
                    loop.close()

                self._last_run = time.time()
                self._run_count += 1

                logger.info(
                    f"NicheCronScheduler: Run #{self._run_count} complete, "
                    f"mutations={self._last_result.get('mutations_applied', 0)}"
                )

            except Exception as e:
                logger.error(f"NicheCronScheduler: Error in auto-update: {e}")

            # Wait for next interval
            self._stop_event.wait(timeout=self._interval * 3600)

    def trigger_now(self) -> Dict[str, Any]:
        """Fuerza una ejecución inmediata (síncrona, para API calls)."""
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(self._updater.auto_update())
            finally:
                loop.close()

            self._last_run = time.time()
            self._run_count += 1
            self._last_result = result
            return result

        except Exception as e:
            return {"error": str(e)}

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del scheduler."""
        return {
            "interval_hours": self._interval,
            "run_count": self._run_count,
            "last_run": self._last_run,
            "last_mutations": self._last_result.get("mutations_applied", 0),
            "is_running": self._thread is not None and self._thread.is_alive(),
        }
