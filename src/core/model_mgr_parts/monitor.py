"""Mixin: Auto-unload monitor methods for ModelManager."""

import time
import threading

from ._imports import logger, ENABLE_AUTO_UNLOAD


class AutoUnloadMixin:
    """Mixin providing auto-unload monitor for idle models."""

    def start_auto_unload_monitor(self):
        """Inicia el thread que monitorea y descarga modelos idle."""
        if not ENABLE_AUTO_UNLOAD:
            logger.info("ModelManager: Auto-unload disabled by config")
            return

        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._auto_unload_loop, daemon=True
        )
        self._monitor_thread.start()
        logger.info(
            f"ModelManager: Auto-unload monitor started "
            f"(timeout={self._idle_timeout_s}s, interval={self._monitor_interval}s)"
        )

    def stop_auto_unload_monitor(self):
        """Detiene el monitor de auto-unload."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
        logger.info("ModelManager: Auto-unload monitor stopped")

    def _auto_unload_loop(self):
        """Loop que descarga modelos tras idle timeout."""
        while not self._stop_event.is_set():
            try:
                self._check_idle_unload()
                self._check_ram_pressure()
            except Exception as e:
                logger.debug(f"Auto-unload monitor error: {e}")

            self._stop_event.wait(timeout=self._monitor_interval)

    def _check_idle_unload(self):
        """Descarga modelos que llevan mucho tiempo sin usarse."""
        now = time.time()

        # Check SemanticEngine idle
        if (self._semantic_engine is not None
                and self._semantic_engine.is_loaded
                and self._semantic_last_access > 0):
            idle_time = now - self._semantic_last_access
            if idle_time > self._idle_timeout_s:
                self.unload_semantic(reason=f"idle_{int(idle_time)}s")
                self._stats["auto_unloads"] += 1

        # Check MiniAIEngine idle
        if (self._mini_ai_engine is not None
                and self._mini_ai_engine.is_loaded
                and self._ai_last_access > 0):
            idle_time = now - self._ai_last_access
            if idle_time > self._idle_timeout_s:
                self.unload_ai(reason=f"idle_{int(idle_time)}s")
                self._stats["auto_unloads"] += 1

    def _check_ram_pressure(self):
        """Si la RAM esta bajo presion, descargar modelos agresivamente."""
        try:
            ram_mb = self._get_current_ram_mb()
            if ram_mb > self._ram_budget_mb * 0.9:
                # RAM al 90% del presupuesto: descargar el modelo mas idle
                logger.warning(
                    f"ModelManager: RAM pressure detected ({ram_mb:.0f}MB / "
                    f"{self._ram_budget_mb}MB budget). Unloading idle models."
                )
                self._stats["ram_budget_exceeded"] += 1

                # Unload the least recently used model
                if (self._semantic_last_access <= self._ai_last_access
                        and self._semantic_engine is not None
                        and self._semantic_engine.is_loaded):
                    self.unload_semantic(reason="ram_pressure")
                elif (self._mini_ai_engine is not None
                      and self._mini_ai_engine.is_loaded):
                    self.unload_ai(reason="ram_pressure")
        except Exception as e:
            logger.debug(f"RAM pressure check error: {e}")
