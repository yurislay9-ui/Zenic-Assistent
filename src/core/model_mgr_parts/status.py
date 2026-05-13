"""Mixin: Eager/lazy init, status and stats for ModelManager."""

import time
from typing import Dict, Any

from ._imports import logger, ENABLE_AUTO_UNLOAD


class StatusMixin:
    """Mixin providing eager init, status and stats methods."""

    def init_eager(self):
        """
        Carga ambos modelos inmediatamente (comportamiento original).
        Usar solo si se quiere el comportamiento v13/v15 sin lazy loading.
        """
        with self._lock:
            self._ensure_semantic_loaded()
            self._ensure_ai_loaded()
        logger.info("ModelManager: Eager init complete (both models loaded)")

    @property
    def semantic_loaded(self) -> bool:
        """True si SemanticEngine esta cargado y listo."""
        return (self._semantic_engine is not None
                and self._semantic_engine.is_loaded)

    @property
    def ai_loaded(self) -> bool:
        """True si MiniAIEngine esta cargado y listo."""
        return (self._mini_ai_engine is not None
                and self._mini_ai_engine.is_loaded)

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadisticas del gestor de modelos."""
        return {
            **self._stats,
            "lazy_load_enabled": self._lazy_load,
            "auto_unload_enabled": ENABLE_AUTO_UNLOAD,
            "idle_timeout_s": self._idle_timeout_s,
            "ram_budget_mb": self._ram_budget_mb,
            "semantic_loaded": self.semantic_loaded,
            "ai_loaded": self.ai_loaded,
            "semantic_idle_s": int(time.time() - self._semantic_last_access) if self._semantic_last_access > 0 else -1,
            "ai_idle_s": int(time.time() - self._ai_last_access) if self._ai_last_access > 0 else -1,
            "current_ram_mb": round(self._get_current_ram_mb(), 1),
        }

    def get_status(self) -> Dict[str, Any]:
        """Estado completo para el endpoint /health."""
        status = {
            "model_manager": "active",
            "mode": "lazy" if self._lazy_load else "eager",
            "ram_current_mb": round(self._get_current_ram_mb(), 1),
            "ram_budget_mb": self._ram_budget_mb,
            "models": {
                "semantic_engine": {
                    "loaded": self.semantic_loaded,
                    "status": "active" if self.semantic_loaded else "unloaded",
                },
                "mini_ai_engine": {
                    "loaded": self.ai_loaded,
                    "status": "active" if self.ai_loaded else "unloaded",
                },
            },
        }
        if self.semantic_loaded:
            status["models"]["semantic_engine"]["idle_s"] = int(
                time.time() - self._semantic_last_access
            ) if self._semantic_last_access > 0 else 0
        if self.ai_loaded:
            status["models"]["mini_ai_engine"]["idle_s"] = int(
                time.time() - self._ai_last_access
            ) if self._ai_last_access > 0 else 0
        return status
