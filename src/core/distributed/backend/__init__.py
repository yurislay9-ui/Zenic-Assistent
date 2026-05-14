"""
ZENIC-AGENTS - Coordination Backend (Abstract + Factory)

Abstract interface for distributed coordination backends and factory
method for creating the appropriate backend based on configuration.

Supports:
    - PostgreSQL: Production backend using pg_advisory_locks, SKIP LOCKED,
      and transactional coordination. Works with the existing docker-compose
      PostgreSQL service.
    - Memory: Single-process in-memory backend for development, testing,
      and graceful degradation when no DB is available.

The factory method CoordinationBackend.create(config) returns the correct
concrete backend, handling import errors gracefully.

All backend operations are protected by retry patterns from the existing
resilience layer (src.core.patterns.resilience.retry).
"""

import logging
from abc import ABC, abstractmethod

from ._types import BackendConfig, BackendType

logger = logging.getLogger("zenic_agents.distributed.backend")

__all__ = [
    "CoordinationBackend",
    "BackendConfig",
    "BackendType",
]


# ============================================================
#  ABSTRACT BACKEND
# ============================================================


from ._core_mixin import CoordinationBackendCoreMixin
from ._extra_mixin import CoordinationBackendExtraMixin


class CoordinationBackend(CoordinationBackendCoreMixin, CoordinationBackendExtraMixin):
    """See module docstring."""
    pass
