"""Mixin: Model unloading methods for ModelManager."""

from ._imports import logger
import logging


class UnloadMixin:
    """Mixin providing model unloading methods."""

    def unload_semantic(self, reason: str = "manual"):
        """Descarga SemanticEngine para liberar ~150MB RAM."""
        with self._lock:
            if self._semantic_engine is not None:
                self._semantic_engine.unload_model()
                self._stats["semantic_unloads"] += 1
                logger.info(f"ModelManager: SemanticEngine unloaded ({reason})")

    def unload_ai(self, reason: str = "manual"):
        """Descarga MiniAIEngine para liberar ~378MB RAM."""
        with self._lock:
            if self._mini_ai_engine is not None:
                self._mini_ai_engine.unload_model()
                self._stats["ai_unloads"] += 1
                logger.info(f"ModelManager: MiniAIEngine unloaded ({reason})")

    def unload_all(self, reason: str = "manual"):
        """Descarga ambos modelos para liberar ~530MB RAM."""
        self.unload_semantic(reason)
        self.unload_ai(reason)
