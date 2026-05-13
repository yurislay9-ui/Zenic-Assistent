"""
Mixin: Model lifecycle methods (load, unload, stats).

FIX (Phase 2): Replaced static `np` import with _get_numpy() lazy loading.
Added retry logic for model loading with exponential backoff.
FIX (v18): Disable ONNX Runtime thread affinity on ARM/Termux to prevent
pthread_setaffinity_np errors and potential crashes.
"""

import os
import time
import logging

# Disable ONNX Runtime thread affinity BEFORE any onnxruntime import.
# On ARM/Termux/proot-distro, thread affinity causes:
#   "pthread_setaffinity_np failed ... error code: 22 Invalid argument"
# Setting this env var must happen before onnxruntime is first loaded.
os.environ.setdefault("ORT_DISABLE_THREAD_AFFINITY", "1")

from ._imports import EMBEDDING_MODEL, EMBEDDING_DIM, INTENT_PROTOTYPES, GOAL_PROTOTYPES, _get_numpy, HAS_NUMPY, logger

# Retry configuration for model loading
_MAX_LOAD_ATTEMPTS = 3
_LOAD_RETRY_BASE_DELAY = 1.0  # seconds
# Maximum prototype embeddings before eviction (Phase 3)
_MAX_PROTOTYPE_ENTRIES = 500
# Maximum embed cache entries (Phase 3 — was 500 implicit)
_MAX_EMBED_CACHE_ENTRIES = 500


class LifecycleMixin:
    """Model lifecycle for SemanticEngine: __init__, load, unload, stats.

    FIX (Phase 3): Added max size limits for _prototype_embeddings and
    _goal_prototype_embeddings to prevent unbounded memory growth.
    Added _evict_prototype_cache() for LRU-style eviction.
    """

    def _init_lifecycle(self, auto_load: bool = True):
        """Initialize lifecycle state (called from SemanticEngine.__init__).

        FIX (Phase 3): Added size tracking for prototype embeddings to
        prevent unbounded memory growth on long-running instances.
        """
        self._model = None
        self._loaded = False
        self._load_time = 0.0
        self._call_count = 0
        self._embed_cache = {}  # Text hash -> embedding cache (bounded by _MAX_EMBED_CACHE_ENTRIES)
        self._prototype_embeddings = {}  # Intent -> mean prototype
        self._goal_prototype_embeddings = {}  # Goal -> mean prototype

        if auto_load:
            self.load_model()

    def load_model(self) -> bool:
        """Carga el modelo de embeddings. Returns True if loaded.

        Includes retry with exponential backoff for transient failures
        (network issues downloading model, OOM on constrained devices).
        """
        if self._loaded and self._model is not None:
            return True

        # Pre-check: if numpy is not available, skip model loading entirely
        # since embeddings require numpy for array operations
        np = _get_numpy()
        if np is None:
            logger.warning(
                "SemanticEngine: numpy not available — skipping model load. "
                "Install numpy to enable embeddings pipeline."
            )
            return False

        last_error = None
        for attempt in range(1, _MAX_LOAD_ATTEMPTS + 1):
            try:
                from fastembed import TextEmbedding
                import warnings
                start = time.time()
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message=".*mean pooling.*", category=UserWarning)
                    self._model = TextEmbedding(model_name=EMBEDDING_MODEL)
                self._load_time = time.time() - start
                self._loaded = True

                # Pre-compute prototype embeddings
                self._build_prototypes()
                # Phase 3: Evict overflow from prototype caches
                self._evict_prototype_cache()

                logger.info(
                    "SemanticEngine: %s loaded in %.1fs (attempt %d)",
                    EMBEDDING_MODEL, self._load_time, attempt
                )
                return True
            except ImportError:
                logger.warning("SemanticEngine: fastembed not installed. Using fallbacks.")
                return False
            except Exception as e:
                last_error = e
                if attempt < _MAX_LOAD_ATTEMPTS:
                    delay = _LOAD_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "SemanticEngine: Model load attempt %d/%d failed: %s. "
                        "Retrying in %.1fs...",
                        attempt, _MAX_LOAD_ATTEMPTS, e, delay
                    )
                    time.sleep(delay)
                else:
                    logger.warning(
                        "SemanticEngine: Failed to load model after %d attempts: %s",
                        _MAX_LOAD_ATTEMPTS, e
                    )

        self._model = None
        return False

    def unload_model(self):
        """Libera el modelo de memoria."""
        if self._model is not None:
            del self._model
            self._model = None
            self._loaded = False
            self._embed_cache.clear()
            self._prototype_embeddings.clear()
            self._goal_prototype_embeddings.clear()
            logger.info("SemanticEngine: Model unloaded")

    def _evict_prototype_cache(self):
        """Evict prototype embeddings if they exceed the limit.

        FIX (Phase 3): Prototype embeddings grew without bound because
        they were only populated at model load time. However, if the
        model is reloaded or prototypes are rebuilt, old entries
        accumulate. This method enforces a size limit.
        """
        for cache in [self._prototype_embeddings, self._goal_prototype_embeddings]:
            if len(cache) > _MAX_PROTOTYPE_ENTRIES:
                # Keep only the most recent entries (last MAX_PROTOTYPE_ENTRIES)
                overflow = len(cache) - _MAX_PROTOTYPE_ENTRIES
                keys = list(cache.keys())[:overflow]
                for k in keys:
                    del cache[k]
                logger.debug(
                    "SemanticEngine: Prototype cache evicted %d entries (limit: %d)",
                    overflow, _MAX_PROTOTYPE_ENTRIES
                )

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self._model is not None

    @property
    def stats(self) -> dict:
        return {
            "model_loaded": self.is_loaded,
            "model_name": EMBEDDING_MODEL if self.is_loaded else "none",
            "load_time_s": self._load_time,
            "total_calls": self._call_count,
            "cache_size": len(self._embed_cache),
            "embedding_dim": EMBEDDING_DIM,
            "numpy_available": HAS_NUMPY,
        }
