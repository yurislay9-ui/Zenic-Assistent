"""
Mixin: Core embedding and similarity methods.

FIX (Phase 2): Replaced static `np` (always None) with _get_numpy() lazy loading.
Now numpy is loaded on first actual use, making the embedding pipeline functional.
"""

import hashlib
import logging

from ._imports import _get_numpy, HAS_NUMPY, logger

# Evict 20% of entries when cache exceeds limit (1/5 = 20%)
_EVICTION_DIVISOR = 5


class EmbedMixin:
    """Core embedding and similarity methods for SemanticEngine."""

    @staticmethod
    def _normalize_embedding(emb, np):
        """Normalize an embedding vector for cosine similarity.

        Divides the vector by its L2 norm. Returns the vector
        unchanged if the norm is zero.

        Args:
            emb: numpy array to normalize.
            np: numpy module reference.

        Returns:
            Normalized numpy array (same object if norm is zero).
        """
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        return emb

    def embed(self, text: str):
        """Genera embedding para un texto. Cached."""
        if not self.is_loaded:
            return None

        np = _get_numpy()
        if np is None:
            return None

        # Check cache — use full hash to avoid collisions from truncated keys
        cache_key = hashlib.sha256(text.encode()).hexdigest()
        if cache_key in self._embed_cache:
            return self._embed_cache[cache_key]

        self._call_count += 1
        try:
            result = list(self._model.embed([text]))
            if result:
                emb = np.array(result[0], dtype=np.float32)
                # Normalize for cosine similarity (faster dot product)
                emb = self._normalize_embedding(emb, np)
                self._embed_cache[cache_key] = emb
                # Limit cache size — evict oldest entries when over limit
                # FIX (Phase 3): Use consistent _MAX_EMBED_CACHE_ENTRIES from lifecycle
                from ._mixin_lifecycle import _MAX_EMBED_CACHE_ENTRIES
                if len(self._embed_cache) > _MAX_EMBED_CACHE_ENTRIES:
                    # Evict 20% of entries (oldest first) — more efficient than
                    # evicting a fixed 100 entries when cache is large
                    evict_count = max(1, len(self._embed_cache) // _EVICTION_DIVISOR)
                    keys = list(self._embed_cache.keys())[:evict_count]
                    for k in keys:
                        del self._embed_cache[k]
                return emb
        except Exception as e:
            logger.warning(f"SemanticEngine: Embedding failed: {e}")
        return None

    def embed_batch(self, texts: list[str]):
        """Genera embeddings para múltiples textos. Más eficiente."""
        if not self.is_loaded:
            return []

        np = _get_numpy()
        if np is None:
            return []

        self._call_count += 1
        try:
            results = list(self._model.embed(texts))
            embeddings = []
            for r in results:
                emb = np.array(r, dtype=np.float32)
                emb = self._normalize_embedding(emb, np)
                embeddings.append(emb)
            return embeddings
        except Exception as e:
            logger.warning(f"SemanticEngine: Batch embedding failed: {e}")
            return []

    @staticmethod
    def similarity(a, b) -> float:
        """Similitud coseno entre dos embeddings normalizados (= dot product)."""
        np = _get_numpy()
        if np is None:
            return 0.0
        return float(np.dot(a, b))

    def similarity_text(self, text_a: str, text_b: str) -> float:
        """Similitud semántica entre dos textos."""
        emb_a = self.embed(text_a)
        emb_b = self.embed(text_b)
        if emb_a is not None and emb_b is not None:
            return self.similarity(emb_a, emb_b)
        return 0.0
