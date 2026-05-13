"""
ZENIC-AGENTS - SmartMemory Main Class

SmartMemory class combining all mixins + session/consolidation/client isolation methods.
Now fully tenant-aware via TenantContext (Phase 2: Real Multitenancy).
"""

import os
import time
import hashlib
import logging
from typing import Optional, Dict, Any, List
from ..types import DB_DIR, DB_PATH, MemoryEntry, logger, IMPORTANCE_THRESHOLD
from ..database import DatabaseMixin
from ..cache import CacheMixin
from ..longterm import LongTermMixin
from ..episodes import EpisodesMixin
from ._tenant_mixin import TenantMixin
from ._session_mixin import SessionMixin
from src.core.tenant._context import get_current_tenant, set_current_tenant, TenantContext

class SmartMemory(DatabaseMixin, CacheMixin, LongTermMixin, EpisodesMixin, TenantMixin, SessionMixin):
    """
    Memoria inteligente para compensar las limitaciones de Qwen3-0.6B.
    
    3 tipos de memoria:
    1. Semantic Cache: "Ya respondí esto antes" → bypass total
    2. Working Memory: "Estamos hablando de X" → contexto para Qwen
    3. Long-term Memory: "La última vez que hicimos X, funcionó Y" → aprendizaje

    Phase 2: Fully tenant-aware. All data is scoped by tenant_id from
    TenantContext. Backward compatible — defaults to '__anonymous__'.
    """

    def __init__(self, semantic_engine=None):
        self._semantic = semantic_engine  # Reference to SemanticEngine for embeddings
        self._session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        self._working_memory: List[MemoryEntry] = []
        self._working_lock = threading.Lock()
        self._client_id = 'default'  # Brecha B: Multi-client isolation
        self._last_vacuum_time = 0.0  # Instance variable (was class var)

        # Phase 2: Tenant-aware initialization
        ctx = get_current_tenant()
        self._tenant_id: str = ctx.effective_tenant_id
        logger.info(
            f"SmartMemory: Initialized with tenant_id='{self._tenant_id}', "
            f"client_id='{self._client_id}'"
        )

        # Initialize DB with WAL mode for better mobile performance
        os.makedirs(DB_DIR, exist_ok=True)
        self._init_db()
        self._enable_wal_mode()
        self._maybe_vacuum()

    def set_client_id(self, client_id: str):
        """Brecha B: Set the client_id for multi-client isolation.
        
        All subsequent DB operations will be scoped to this client.
        Validates that client_id is a non-empty string.
        """
        if not isinstance(client_id, str) or not client_id.strip():
            raise ValueError("client_id must be a non-empty string")
        self._client_id = client_id.strip()
        logger.info(f"SmartMemory: client_id set to '{self._client_id}'")

# Re-export threading for the class
import threading
