"""Mixin: RAM budget management for ModelManager."""

import time
import gc
import platform

from ._imports import logger


class RAMMixin:
    """Mixin providing RAM budget checking and management."""

    def _check_ram_budget(self, needed_mb: int) -> bool:
        """Verifica si hay presupuesto de RAM para cargar un modelo."""
        current_mb = self._get_current_ram_mb()
        return (current_mb + needed_mb) <= self._ram_budget_mb

    def _try_free_ram(self, needed_mb: int):
        """Intenta liberar RAM descargando modelos menos usados.

        FIX (v18.1): Changed gc.collect(2) to gc.collect(0) to avoid
        crashing llama-cpp-python's C extension on ARM/Termux during
        object finalization. Full GC after unloading models is safe
        because the model's C objects are already deleted by unload_model().
        But just in case, we use gen-0 which is much safer.
        """
        # Strategy: unload least recently used model first
        sem_idle = time.time() - self._semantic_last_access if self._semantic_last_access > 0 else 9999
        ai_idle = time.time() - self._ai_last_access if self._ai_last_access > 0 else 9999

        # Unload the most idle model
        if sem_idle >= ai_idle and self._semantic_engine and self._semantic_engine.is_loaded:
            self.unload_semantic(reason="free_ram_for_ai")
        elif self._mini_ai_engine and self._mini_ai_engine.is_loaded:
            self.unload_ai(reason="free_ram_for_semantic")

        # Light GC after model unload — models are already freed so this is safe
        gc.collect(0)

    @staticmethod
    def _get_current_ram_mb() -> float:
        """Obtiene el uso actual de RAM del proceso en MB."""
        try:
            with open('/proc/self/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        return int(line.split()[1]) / 1024
        except (FileNotFoundError, PermissionError):
            pass
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            if platform.system() == 'Darwin':
                return usage.ru_maxrss / 1024 / 1024  # macOS: bytes -> MB
            return usage.ru_maxrss / 1024  # Linux: KB -> MB
        except Exception:
            pass
        return 0.0
