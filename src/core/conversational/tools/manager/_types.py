"""Types and constants for manager."""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any
from ..types.tool_use import ToolPermission, ToolSpec

logger = logging.getLogger("zenic_agents.conversational.tools.manager")

@dataclass
class ToolManagerConfig:
    """Configuracion del ToolManager."""
    default_timeout: float = 30.0
    max_concurrent: int = 3
    allow_dangerous: bool = False
    auto_register_builtins: bool = True



@dataclass
class ToolResolution:
    """Resultado de resolver una tool call desde el pipeline."""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    permission: ToolPermission = ToolPermission.ALLOWED
    spec: ToolSpec | None = None
    needs_confirmation: bool = False
    error: str = ""
