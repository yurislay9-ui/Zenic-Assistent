"""
ZENIC-AGENTS - AgentCache

Cache semántico para resultados de agentes.
Evita llamadas repetidas al LLM para consultas similares.
"""

import hashlib
import time
import threading
import logging
from collections import OrderedDict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Configuración del cache
MAX_CACHE_SIZE = 500          # Máximo de entradas en cache
DEFAULT_TTL_SECONDS = 3600   # 1 hora de vida útil
SIMILARITY_THRESHOLD = 0.85  # Umbral para cache hit semántico


class AgentCache:
    """
    Cache de resultados de agentes.

    Dos modos de lookup:
    1. Exacto: Hash SHA256 del input → resultado directo
    2. Semántico: Si hay SemanticEngine disponible, usa embeddings

    El cache es deliberadamente simple para funcionar en hardware
    restringido (Xiaomi Redmi 12R Pro, 12GB RAM).
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS,
                 max_size: int = MAX_CACHE_SIZE) -> None:
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._hits = 0
        self._misses = 0
        self._semantic_engine = None
        self._lock = threading.Lock()

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / max(self._hits + self._misses, 1),
        }

    def set_semantic_engine(self, engine) -> None:
        """Cablea el SemanticEngine para cache semántico."""
        self._semantic_engine = engine

    def get(self, agent_name: str, input_data: Any) -> Optional[Any]:
        """
        Busca en el cache por agente y input.

        Args:
            agent_name: Nombre del agente
            input_data: Datos de entrada

        Returns:
            Resultado cacheado o None
        """
        key = self._make_key(agent_name, input_data)

        # 1. Lookup exacto (thread-safe)
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                if not self._is_expired(entry):
                    self._hits += 1
                    # Move to end for LRU behavior (most recently used at end)
                    self._cache.move_to_end(key)
                    return entry["result"]
                else:
                    # Expirado, eliminar dentro del lock
                    del self._cache[key]

        # 2. Lookup semántico (si hay engine disponible)
        if self._semantic_engine and self._semantic_engine.is_loaded:
            sem_result = self._semantic_lookup(agent_name, input_data)
            if sem_result is not None:
                with self._lock:
                    self._hits += 1
                return sem_result

        with self._lock:
            self._misses += 1
        return None

    def put(self, agent_name: str, input_data: Any, result: Any) -> None:
        """
        Almacena un resultado en el cache.

        Args:
            agent_name: Nombre del agente
            input_data: Datos de entrada
            result: Resultado a cachear
        """
        key = self._make_key(agent_name, input_data)

        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)

            # Evitar que el cache crezca demasiado
            if len(self._cache) >= self._max_size:
                self._evict_oldest()

            self._cache[key] = {
                "agent": agent_name,
                "result": result,
                "timestamp": time.time(),
                "access_count": 0,
                "input_text": self._serialize(input_data)[:500],
            }

    def clear(self) -> None:
        """Limpia todo el cache."""
        self._cache.clear()
        logger.debug("AgentCache: Cleared")

    def __len__(self) -> int:
        """Return the number of entries in the cache."""
        return len(self._cache)

    def _make_key(self, agent_name: str, input_data: Any) -> str:
        """Genera una clave hash para el cache."""
        # Serializar input de forma determinista
        input_str = f"{agent_name}:{self._serialize(input_data)}"
        return hashlib.sha256(input_str.encode()).hexdigest()[:32]

    @staticmethod
    def _serialize(data: Any) -> str:
        """Serializa datos para hashing de forma determinista."""
        import json
        if isinstance(data, str):
            return data
        if hasattr(data, '__dict__'):
            # dataclass o objeto
            try:
                return json.dumps(data.__dict__, sort_keys=True, default=str)
            except (TypeError, ValueError):
                return str(data)
        return str(data)

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """Verifica si una entrada ha expirado."""
        age = time.time() - entry.get("timestamp", 0)
        return age > self._ttl

    def _evict_oldest(self) -> None:
        """Elimina la entrada más antigua (LRU) — O(1) con OrderedDict.
        
        OrderedDict maintains insertion order; oldest items are at the front.
        Since we move accessed items to the end via move_to_end(), this
        naturally implements LRU eviction.
        """
        if not self._cache:
            return
        # Pop the first (oldest/least recently used) item — O(1)
        self._cache.popitem(last=False)

    def _semantic_lookup(self, agent_name: str,
                         input_data: Any) -> Optional[Any]:
        """
        Busca en el cache usando similitud semántica.

        Solo funciona si SemanticEngine está disponible.
        Compara el input con todos los inputs cacheados del mismo agente.
        """
        if not self._semantic_engine or not self._semantic_engine.is_loaded:
            return None

        # Obtener texto del input
        input_text = str(input_data) if not isinstance(input_data, str) else input_data
        if not input_text or len(input_text) < 5:
            return None

        best_match = None
        best_score = 0.0

        for key, entry in self._cache.items():
            if entry.get("agent") != agent_name:
                continue
            if self._is_expired(entry):
                continue

            # Comparar usando SemanticEngine
            # Usamos el input original almacenado si está disponible
            cached_input = entry.get("input_text", "")
            if not cached_input:
                continue

            try:
                score = self._semantic_engine.compute_similarity(input_text, cached_input)
                if score > best_score and score >= SIMILARITY_THRESHOLD:
                    best_score = score
                    best_match = entry["result"]
            except Exception:
                continue

        return best_match
