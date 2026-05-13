"""
Tipos de tool-use del asistente.

Modela las herramientas que el asistente puede usar,
los permisos, las llamadas y los resultados.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ToolPermission(str, Enum):
    """Niveles de permiso para herramientas."""
    ALLOWED = "allowed"          # Ejecucion libre
    CONFIRM_REQUIRED = "confirm"  # Requiere confirmacion del usuario
    DENIED = "denied"            # No permitido


@dataclass
class ToolSpec:
    """
    Especificacion de una herramienta disponible.

    Define el nombre, descripcion, parametros y permisos
    de una herramienta que el asistente puede invocar.
    """
    name: str = ""
    description: str = ""
    category: str = "general"   # general, code, web, data, system
    parameters: dict[str, Any] = field(default_factory=dict)
    permission: ToolPermission = ToolPermission.CONFIRM_REQUIRED
    enabled: bool = True
    rate_limit: int = 0         # Max llamadas por minuto (0 = sin limite)
    timeout_seconds: float = 30.0

    @property
    def needs_confirmation(self) -> bool:
        return self.permission == ToolPermission.CONFIRM_REQUIRED

    @property
    def is_dangerous(self) -> bool:
        return self.category == "system" or self.permission == ToolPermission.DENIED

    def to_openai_format(self) -> dict[str, Any]:
        """Convierte a formato OpenAI function calling."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolCall:
    """
    Llamada a una herramienta por el asistente.

    Representa la invocacion de una herramienta con
    sus argumentos y estado de ejecucion.
    """
    call_id: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    status: str = "pending"      # pending, running, completed, failed, denied
    result: Any = None
    error: str = ""
    duration_ms: float = 0.0

    def to_openai_format(self) -> dict[str, Any]:
        """Convierte a formato OpenAI tool call."""
        return {
            "id": self.call_id,
            "type": "function",
            "function": {
                "name": self.tool_name,
                "arguments": str(self.arguments),
            },
        }


@dataclass
class ToolResult:
    """
    Resultado de la ejecucion de una herramienta.

    Contiene el output, estado, duracion y metadata
    de la ejecucion de una herramienta.
    """
    call_id: str = ""
    tool_name: str = ""
    success: bool = False
    output: Any = None
    error: str = ""
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def is_error(self) -> bool:
        return not self.success or bool(self.error)

    def to_openai_format(self) -> dict[str, Any]:
        """Convierte a formato OpenAI tool result."""
        content = str(self.output) if self.success else f"Error: {self.error}"
        return {
            "tool_call_id": self.call_id,
            "role": "tool",
            "content": content,
        }


# ─── Herramientas integradas del asistente ────────────────────

BUILTIN_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="web_search",
        description="Buscar informacion en la web",
        category="web",
        permission=ToolPermission.ALLOWED,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Consulta de busqueda"},
                "max_results": {"type": "integer", "description": "Max resultados", "default": 5},
            },
            "required": ["query"],
        },
    ),
    ToolSpec(
        name="code_execute",
        description="Ejecutar codigo Python en sandbox aislado",
        category="code",
        permission=ToolPermission.CONFIRM_REQUIRED,
        timeout_seconds=15.0,
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Codigo Python a ejecutar"},
                "language": {"type": "string", "description": "Lenguaje", "default": "python"},
            },
            "required": ["code"],
        },
    ),
    ToolSpec(
        name="calculator",
        description="Realizar calculos matematicos",
        category="general",
        permission=ToolPermission.ALLOWED,
        parameters={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Expresion matematica"},
            },
            "required": ["expression"],
        },
    ),
    ToolSpec(
        name="file_read",
        description="Leer contenido de un archivo del proyecto",
        category="system",
        permission=ToolPermission.CONFIRM_REQUIRED,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del archivo"},
            },
            "required": ["path"],
        },
    ),
    ToolSpec(
        name="memory_recall",
        description="Buscar en la memoria del asistente",
        category="general",
        permission=ToolPermission.ALLOWED,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Consulta de busqueda en memoria"},
                "memory_type": {"type": "string", "description": "Tipo de memoria", "default": "all"},
            },
            "required": ["query"],
        },
    ),
]
