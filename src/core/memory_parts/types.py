"""
ZENIC-AGENTS - SmartMemory Types & Constants

Memoria inteligente que APOYA a Qwen3-0.6B compensando sus limitaciones:
- Contexto limitado → SmartMemory almacena y recupera contexto relevante
- Sin aprendizaje → SmartMemory aprende de interacciones previas
- Sin estado → SmartMemory mantiene estado entre sesiones

Arquitectura de 3 capas:
  Capa 1: SemanticEngine → ENTIENDE (embeddings, similitud)
  Capa 2: MiniAIEngine (Qwen) → PIENSA (razonamiento)
  Capa 3: SmartMemory → RECUERDA (cache semántico, contexto, aprendizaje)

Características:
  1. Semantic Cache: Si ya respondimos algo similar → devolver cacheado
  2. Working Memory: Contexto de la tarea actual (últimos N intercambios)
  3. Long-term Memory: Soluciones previas exitosas indexadas por semántica
  4. Importance Scoring: No todo es igual de importante → priorizar
  5. Auto-compress: Resumir contexto largo para que Qwen no se sature
  6. SQLite persistente: Sobrevive reinicios

Optimizado para:
  - Xiaomi Redmi 12R Pro (12+8GB)
  - Qwen3-0.6B con contexto de 2048 tokens
  - ~100KB por sesión de trabajo
"""

import os
import logging
from typing import Optional, Any
from dataclasses import dataclass

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    np = None
    HAS_NUMPY = False

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "db")
DB_PATH = os.path.join(DB_DIR, "smart_memory.sqlite")

# Limits for Qwen3-0.6B context window
MAX_WORKING_ENTRIES = 20       # Max entries in working memory
MAX_COMPRESSED_TOKENS = 500    # Max tokens for compressed context
IMPORTANCE_THRESHOLD = 0.6     # Min importance to promote to long-term
SEMANTIC_CACHE_THRESHOLD = 0.85 # Min similarity for cache hit
MAX_LONG_TERM_ENTRIES = 500    # Max entries in long-term memory
MAX_EPISODIC_ENTRIES = 200     # Max entries in episodic memory
MAX_PROCEDURAL_ENTRIES = 100   # Max entries in procedural memory
MAX_PROJECT_ENTRIES = 50       # Max entries in project memory


@dataclass
class MemoryEntry:
    """Una entrada en la memoria."""
    id: Optional[int] = None
    query: str = ""
    response: str = ""
    operation: str = ""
    goal: str = ""
    importance: float = 0.5     # 0.0-1.0, higher = more important
    timestamp: float = 0.0
    embedding: Optional[Any] = None  # np.ndarray when numpy available
    access_count: int = 0
    session_id: str = ""
    client_id: str = "default"
    tenant_id: str = "__anonymous__"
