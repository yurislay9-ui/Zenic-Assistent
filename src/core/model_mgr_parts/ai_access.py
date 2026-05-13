"""Mixin: MiniAIEngine access methods for ModelManager."""

import time
from contextlib import contextmanager

from ._imports import logger


class AIAccessMixin:
    """Mixin providing MiniAIEngine lazy-load and context access."""

    @property
    def mini_ai_engine(self):
        """
        Acceso directo al MiniAIEngine. Carga lazy si es necesario.
        Para acceso con auto-unload protegido, usar ai_engine_ctx().
        """
        with self._lock:
            self._ensure_ai_loaded()
            self._ai_last_access = time.time()
            return self._mini_ai_engine

    @contextmanager
    def ai_engine_ctx(self):
        """
        Context manager para MiniAIEngine con auto-unload tracking.

        Uso:
            with manager.ai_engine_ctx() as engine:
                if engine and engine.is_loaded:
                    result = engine.classify_intent(text)
        """
        with self._lock:
            self._ensure_ai_loaded()
            self._ai_last_access = time.time()
        try:
            yield self._mini_ai_engine
        finally:
            self._ai_last_access = time.time()

    def _ensure_ai_loaded(self):
        """Carga MiniAIEngine si no esta cargado (lazy loading)."""
        if self._mini_ai_engine is not None and self._mini_ai_engine.is_loaded:
            return

        # Check RAM budget before loading
        if not self._check_ram_budget(400):  # Qwen needs ~400MB
            logger.warning(
                "ModelManager: RAM budget exceeded, cannot load MiniAIEngine. "
                "Will try unloading SemanticEngine first."
            )
            self._try_free_ram(needed_mb=400)

        from src.core.mini_ai_engine import MiniAIEngine
        self._mini_ai_engine = MiniAIEngine(auto_load=True)
        self._ai_last_access = time.time()
        self._stats["ai_loads"] += 1

        if self._mini_ai_engine.is_loaded:
            logger.info("ModelManager: MiniAIEngine loaded (lazy)")
        else:
            logger.warning("ModelManager: MiniAIEngine load failed, using fallbacks")
