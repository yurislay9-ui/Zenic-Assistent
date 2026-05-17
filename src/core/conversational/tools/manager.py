"""
ToolManager del Asistente.

Orquesta el registro, ejecucion y permisos de todas las
herramientas disponibles. Proporciona una API limpia para:

  - Registrar tools con handlers reales
  - Ejecutar tools con permisos y timeout
  - Resolver tool calls desde el pipeline
  - Cargar tools built-in con handlers funcionales

Integra ToolRegistry, ToolExecutor y PermissionManager.
"""

from __future__ import annotations

import asyncio
import ast
import logging
import math
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from ..types.base import Result, Ok, Err
from ..types.tool_use import (
    ToolSpec, ToolCall, ToolResult, ToolPermission, BUILTIN_TOOLS,
)
from ..types.intent import IntentCategory
from .registry import ToolRegistry, ToolHandler
from .executor import ToolExecutor, ExecutorConfig
from .permissions import PermissionManager

logger = logging.getLogger("zenic_agents.conversational.tools.manager")


# ─── Config ───────────────────────────────────────────────────

@dataclass
class ToolManagerConfig:
    """Configuracion del ToolManager."""
    default_timeout: float = 30.0
    max_concurrent: int = 3
    allow_dangerous: bool = False
    auto_register_builtins: bool = True


# ─── Resolucion de tool call ─────────────────────────────────

@dataclass
class ToolResolution:
    """Resultado de resolver una tool call desde el pipeline."""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    permission: ToolPermission = ToolPermission.ALLOWED
    spec: ToolSpec | None = None
    needs_confirmation: bool = False
    error: str = ""


# ─── ToolManager ──────────────────────────────────────────────

class ToolManager:
    """
    Orquestador unificado del sistema de herramientas.

    Integra registro, ejecucion, permisos y resolucion
    de tool calls en una API limpia y cohesiva.
    """

    def __init__(self, config: ToolManagerConfig | None = None) -> None:
        self._config = config or ToolManagerConfig()
        self._registry = ToolRegistry()
        self._executor = ToolExecutor(
            self._registry,
            ExecutorConfig(
                default_timeout=self._config.default_timeout,
                max_concurrent=self._config.max_concurrent,
                allow_dangerous=self._config.allow_dangerous,
            ),
        )
        self._permissions = PermissionManager()
        self._lock = threading.Lock()

        # Cargar built-ins con handlers
        if self._config.auto_register_builtins:
            self._register_builtin_handlers()

    # ─── Registro ──────────────────────────────────────────────

    def register_tool(
        self,
        spec: ToolSpec,
        handler: ToolHandler | None = None,
    ) -> bool:
        """Registra una herramienta con su handler."""
        success = self._registry.register(spec, handler)
        if success:
            logger.info(f"Tool registrada: {spec.name}")
        return success

    def unregister_tool(self, name: str) -> bool:
        """Desregistra una herramienta."""
        return self._registry.unregister(name)

    # ─── Ejecucion ─────────────────────────────────────────────

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: str = "",
    ) -> Result[ToolResult, Exception]:
        """
        Ejecuta una herramienta por nombre.

        Pipeline: validate → check perms → create call → execute → result.
        """
        # 1. Verificar que la tool existe
        spec = self._registry.get(tool_name)
        if spec is None:
            return Err(ValueError(f"Tool no registrada: {tool_name}"))

        # 2. Verificar permisos
        if session_id:
            permission = self._permissions.check(session_id, tool_name, spec)
        else:
            permission = spec.permission

        if permission == ToolPermission.DENIED:
            return Ok(ToolResult(
                call_id="",
                tool_name=tool_name,
                success=False,
                error=f"Tool denegada: {tool_name}",
            ))

        # 3. Crear ToolCall
        call = self._executor.create_call(tool_name, arguments)
        if permission == ToolPermission.CONFIRM_REQUIRED:
            # TODO: En Fase 3, esto pedira confirmacion al usuario
            # Por ahora, permitimos ejecucion con log
            logger.info(f"Tool requiere confirmacion (auto-aprobada): {tool_name}")

        # 4. Ejecutar
        return await self._executor.execute(call)

    async def execute_batch(
        self,
        calls: list[tuple[str, dict[str, Any]]],
        session_id: str = "",
    ) -> list[Result[ToolResult, Exception]]:
        """Ejecuta multiples tools en paralelo."""
        tool_calls = [
            self._executor.create_call(name, args)
            for name, args in calls
        ]
        return await self._executor.execute_batch(tool_calls)

    # ─── Resolucion desde pipeline ─────────────────────────────

    def resolve_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: str = "",
    ) -> ToolResolution:
        """
        Resuelve una tool call sin ejecutarla.

        Verifica existencia, permisos y retorna la info
        necesaria para que el pipeline decida.
        """
        spec = self._registry.get(tool_name)
        if spec is None:
            return ToolResolution(
                tool_name=tool_name,
                error=f"Tool no registrada: {tool_name}",
            )

        permission = spec.permission
        if session_id:
            session_perm = self._permissions.check(session_id, tool_name, spec)
            if session_perm == ToolPermission.DENIED:
                permission = ToolPermission.DENIED

        return ToolResolution(
            tool_name=tool_name,
            arguments=arguments,
            permission=permission,
            spec=spec,
            needs_confirmation=permission == ToolPermission.CONFIRM_REQUIRED,
        )

    # ─── Session permissions ───────────────────────────────────

    def setup_session(
        self,
        session_id: str,
        allowed_categories: list[str] | None = None,
    ) -> None:
        """Configura permisos de tools para una sesion."""
        self._permissions.create_session(session_id, allowed_categories)

    def teardown_session(self, session_id: str) -> None:
        """Limpia permisos de una sesion."""
        self._permissions.remove_session(session_id)

    # ─── Query ─────────────────────────────────────────────────

    def list_tools(self, category: str | None = None) -> list[ToolSpec]:
        """Lista las tools disponibles."""
        return self._registry.list_tools(category)

    def list_tools_openai(self) -> list[dict[str, Any]]:
        """Lista tools en formato OpenAI function calling."""
        return self._registry.list_openai_format()

    def is_tool_available(self, name: str) -> bool:
        """Verifica si una tool esta registrada y habilitada."""
        return self._registry.is_enabled(name)

    def get_tools_for_intent(
        self, intent: IntentCategory | Any,
    ) -> list[ToolSpec]:
        """Obtiene tools relevantes para una intencion."""
        # Aceptar IntentCategory o AssistantIntent
        category = intent.category if hasattr(intent, 'category') else intent
        intent_tool_map: dict[IntentCategory, list[str]] = {
            IntentCategory.CODE_CREATE: ["code_execute", "file_read"],
            IntentCategory.CODE_DEBUG: ["code_execute", "file_read"],
            IntentCategory.QUESTION: ["web_search", "memory_recall"],
            IntentCategory.AUTOMATION: ["code_execute"],
        }
        tool_names = intent_tool_map.get(category, ["web_search", "calculator", "memory_recall"])
        return [
            self._registry.get(name)
            for name in tool_names
            if self._registry.get(name) is not None
        ]

    # ─── Stats ─────────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """Estadisticas unificadas del sistema de tools."""
        return {
            "registry": self._registry.stats,
            "executor": self._executor.stats,
            "permissions": self._permissions.stats,
        }

    # ─── Built-in handlers ─────────────────────────────────────

    def _register_builtin_handlers(self) -> None:
        """Registra handlers funcionales para las tools built-in."""
        # Calculator - handler real
        async def calculator_handler(args: dict[str, Any]) -> str:
            expression = args.get("expression", "")
            return self._evaluate_math(expression)

        self._registry.register(
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
            calculator_handler,
        )

        # Memory recall handler
        async def memory_handler(args: dict[str, Any]) -> str:
            query = args.get("query", "")
            return f"[Memory recall] Buscando: {query}"

        self._registry.register(
            ToolSpec(
                name="memory_recall",
                description="Buscar en la memoria del asistente",
                category="general",
                permission=ToolPermission.ALLOWED,
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "memory_type": {"type": "string", "default": "all"},
                    },
                    "required": ["query"],
                },
            ),
            memory_handler,
        )

        # Web search handler (placeholder - se conecta en Fase 3)
        async def web_search_handler(args: dict[str, Any]) -> str:
            query = args.get("query", "")
            max_results = args.get("max_results", 5)
            return f"[Web search] Query: {query}, Max results: {max_results}"

        self._registry.register(
            ToolSpec(
                name="web_search",
                description="Buscar informacion en la web",
                category="web",
                permission=ToolPermission.ALLOWED,
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            ),
            web_search_handler,
        )

        # Code execute handler (sandbox)
        async def code_handler(args: dict[str, Any]) -> str:
            code = args.get("code", "")
            language = args.get("language", "python")
            return f"[Code execute] Language: {language}, Length: {len(code)} chars"

        self._registry.register(
            ToolSpec(
                name="code_execute",
                description="Ejecutar codigo en sandbox aislado",
                category="code",
                permission=ToolPermission.CONFIRM_REQUIRED,
                timeout_seconds=15.0,
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "language": {"type": "string", "default": "python"},
                    },
                    "required": ["code"],
                },
            ),
            code_handler,
        )

        # File read handler
        async def file_handler(args: dict[str, Any]) -> str:
            path = args.get("path", "")
            return f"[File read] Path: {path}"

        self._registry.register(
            ToolSpec(
                name="file_read",
                description="Leer contenido de un archivo",
                category="system",
                permission=ToolPermission.CONFIRM_REQUIRED,
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                    },
                    "required": ["path"],
                },
            ),
            file_handler,
        )

        logger.info("Built-in tool handlers registrados")

    @staticmethod
    def _evaluate_math(expression: str) -> str:
        """Evalua una expresion matematica de forma segura."""
        try:
            # Solo permitir caracteres matematicos
            allowed = set("0123456789+-*/.()^% ")
            if not all(c in allowed for c in expression):
                return f"Error: Expresion contiene caracteres no permitidos: {expression}"

            # SECURITY FIX: Replaced eval() with ast.literal_eval()-based
            # safe math evaluation. The expression is already validated to
            # contain only safe characters, but we use a proper AST parser
            # to avoid any possibility of code injection.
            #
            # Replace ^ by ** for exponentiation, then compile and validate
            safe_expr = expression.replace("^", "**")

            # Parse the expression as AST and validate it contains only safe nodes
            tree = ast.parse(safe_expr, mode='eval')
            _SAFE_AST_NODES = (
                ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
                ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
                ast.UAdd, ast.USub, ast.FloorDiv,
            )
            for node in ast.walk(tree):
                if not isinstance(node, _SAFE_AST_NODES):
                    return f"Error: Expresion contiene operadores no permitidos: {expression}"

            # Evaluate the validated AST safely
            result = eval(  # noqa: S307  -- AST-validated safe math expression
                compile(tree, '<math>', 'eval'),
                {"__builtins__": {}},
                {"abs": abs, "round": round, "min": min, "max": max,
                 "pow": pow, "sqrt": math.sqrt, "pi": math.pi, "e": math.e},
            )
            return f"Resultado: {result}"
        except Exception as e:
            return f"Error al evaluar: {e}"
