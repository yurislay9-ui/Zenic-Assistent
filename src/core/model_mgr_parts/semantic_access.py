"""Mixin: SemanticEngine access methods for ModelManager."""

import time
from contextlib import contextmanager

from ._imports import logger


class SemanticAccessMixin:
    """Mixin providing SemanticEngine lazy-load and context access."""

    @property
    def semantic_engine(self):
        """
        Acceso directo al SemanticEngine. Carga lazy si es necesario.
        Para acceso con auto-unload protegido, usar semantic_engine_ctx().
        """
        with self._lock:
            self._ensure_semantic_loaded()
            self._semantic_last_access = time.time()
            return self._semantic_engine

    @contextmanager
    def semantic_engine_ctx(self):
        """
        Context manager para SemanticEngine con auto-unload tracking.

        Uso:
            with manager.semantic_engine_ctx() as engine:
                if engine and engine.is_loaded:
                    result = engine.classify_intent(text)
        """
        with self._lock:
            self._ensure_semantic_loaded()
            self._semantic_last_access = time.time()
        try:
            yield self._semantic_engine
        finally:
            self._semantic_last_access = time.time()

    def _ensure_semantic_loaded(self):
        """Carga SemanticEngine si no esta cargado (lazy loading)."""
        if self._semantic_engine is not None and self._semantic_engine.is_loaded:
            return

        # Check RAM budget before loading
        if not self._check_ram_budget(150):  # fastembed needs ~150MB
            logger.warning(
                "ModelManager: RAM budget exceeded, cannot load SemanticEngine. "
                "Will try unloading AI engine first."
            )
            self._try_free_ram(needed_mb=150)

        from src.core.semantic_engine import SemanticEngine
        self._semantic_engine = SemanticEngine(auto_load=True)
        self._semantic_last_access = time.time()
        self._stats["semantic_loads"] += 1

        if self._semantic_engine.is_loaded:
            logger.info("ModelManager: SemanticEngine loaded (lazy)")
        else:
            logger.warning("ModelManager: SemanticEngine load failed, using fallbacks")
