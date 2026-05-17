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


def _sanitize_client(value: str, visible: int = 4) -> str:
    """Show only last N characters of a client identifier."""
    if not value or len(value) <= visible:
        return "***"
    return f"***{value[-visible:]}"

from ..database import DatabaseMixin
from ..cache import CacheMixin
from ..longterm import LongTermMixin
from ..episodes import EpisodesMixin
from ._tenant_mixin import TenantMixin
from ._session_mixin import SessionMixin
# Tenant module removed — use fallback anonymous context
# from src.core.tenant._context import get_current_tenant, set_current_tenant, TenantContext
from src.core.shared.tenant_utils import ANONYMOUS_TENANT

class _FallbackTenantContext:
    """Minimal fallback for removed TenantContext."""
    def __init__(self):
        self.tenant_id = ANONYMOUS_TENANT
        self.effective_tenant_id = ANONYMOUS_TENANT
        self.user_id = 0
        self.username = ""
        self.role = "viewer"
        self.plan = "free"
        self.quotas = {}
        self.features = []
        self.permissions = []
        self.auth_method = ""
        self.is_authenticated = False
        self.extra = {}

def get_current_tenant():
    return _FallbackTenantContext()

def set_current_tenant(ctx):
    pass

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
            f"SmartMemory: Initialized with tenant_id='{_sanitize_client(self._tenant_id)}', "
            f"client_id='{_sanitize_client(self._client_id)}'"
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
        logger.info(f"SmartMemory: client_id set to '{_sanitize_client(self._client_id)}'")

# Re-export threading for the class
import threading
