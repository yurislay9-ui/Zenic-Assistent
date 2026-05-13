"""
ZENIC-AGENTS - Sandbox Isolation v16 — Facade

Sistema de aislamiento completo para el sandbox.

This module is a thin facade; all logic lives in sandbox_parts/.

FIX (Phase 4): Removed redundant star import that was followed by
explicit imports of the same names. The explicit imports are preferred
for clarity and static analysis support.
"""

from .sandbox_parts import (
    SandboxWorkspace, SandboxIsolationManager,
    get_isolation_manager, shutdown_isolation,
    create_sandbox_builtins, create_sandbox_globals,
)

__all__ = [
    "SandboxWorkspace", "SandboxIsolationManager",
    "get_isolation_manager", "shutdown_isolation",
    "create_sandbox_builtins", "create_sandbox_globals",
]
