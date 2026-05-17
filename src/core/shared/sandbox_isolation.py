"""
Zenic-Agents — Sandbox Isolation (Facade)

Sistema de aislamiento para el sandbox.
If sandbox_parts/ is not available, provides stub implementations.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from .sandbox_parts import (  # type: ignore[import-unresolved]
        SandboxWorkspace, SandboxIsolationManager,
        get_isolation_manager, shutdown_isolation,
        create_sandbox_builtins, create_sandbox_globals,
    )
except ImportError:
    logger.warning("sandbox_parts not available — using stub implementations")

    class SandboxWorkspace:  # type: ignore[no-redef]
        """Stub SandboxWorkspace when sandbox_parts is not available."""
        def __init__(self, **kwargs: Any) -> None: ...
        def isolate(self, *args: Any, **kwargs: Any) -> Any: return {}

    class SandboxIsolationManager:  # type: ignore[no-redef]
        """Stub SandboxIsolationManager when sandbox_parts is not available."""
        def __init__(self, **kwargs: Any) -> None: ...
        def create_workspace(self, *args: Any, **kwargs: Any) -> SandboxWorkspace:
            return SandboxWorkspace()

    def get_isolation_manager() -> SandboxIsolationManager:  # type: ignore[misc]
        return SandboxIsolationManager()

    def shutdown_isolation() -> None:  # type: ignore[misc]
        pass

    def create_sandbox_builtins() -> Dict[str, Any]:  # type: ignore[misc]
        return {}

    def create_sandbox_globals() -> Dict[str, Any]:  # type: ignore[misc]
        return {}

__all__ = [
    "SandboxWorkspace", "SandboxIsolationManager",
    "get_isolation_manager", "shutdown_isolation",
    "create_sandbox_builtins", "create_sandbox_globals",
]
