"""
Ejecutor de herramientas del Asistente.

Ejecuta las tools registradas con:
  - Timeout enforcement
  - Permission checking
  - Resultado tipado (ToolResult)
  - Metricas de ejecucion
  - Ejecucion concurrente limitada
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..types.base import Result, Ok, Err
from ..types.tool_use import ToolCall, ToolResult, ToolPermission
from ..config.constants import TOOL_EXECUTION_TIMEOUT, TOOL_MAX_CONCURRENT
from .registry import ToolRegistry

logger = logging.getLogger("zenic_agents.conversational.tools.executor")


# ─── Config ──────────────────────────────────────────────────

@dataclass
class ExecutorConfig:
    """Configuracion del ejecutor."""
    default_timeout: float = TOOL_EXECUTION_TIMEOUT
    max_concurrent: int = TOOL_MAX_CONCURRENT
    allow_dangerous: bool = False


# ─── Ejecutor ────────────────────────────────────────────────

class ToolExecutor:
    """
    Ejecutor de herramientas.

    Ejecuta tools con timeout, permisos y metricas.
    Garantiza que ninguna tool se cuelga indefinidamente.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        config: ExecutorConfig | None = None,
    ) -> None:
        self._registry = registry
        self._config = config or ExecutorConfig()
        self._running_count = 0
        self._stats = {
            "total_executed": 0,
            "total_success": 0,
            "total_failed": 0,
            "total_denied": 0,
            "total_timeout": 0,
        }

    async def execute(self, call: ToolCall) -> Result[ToolResult, Exception]:
        """
        Ejecuta una llamada a herramienta.

        Pipeline: validate → check permission → acquire slot → execute → result.
        """
        self._stats["total_executed"] += 1
        start_time = time.time()

        # 1. Validar que la tool existe
        spec = self._registry.get(call.tool_name)
        if spec is None:
            self._stats["total_failed"] += 1
            return Err(ValueError(f"Tool no encontrada: {call.tool_name}"))

        # 2. Verificar permisos
        if not spec.enabled:
            self._stats["total_denied"] += 1
            return Ok(ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                success=False,
                error=f"Tool deshabilitada: {call.tool_name}",
                duration_ms=(time.time() - start_time) * 1000,
            ))

        if spec.is_dangerous and not self._config.allow_dangerous:
            self._stats["total_denied"] += 1
            return Ok(ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                success=False,
                error=f"Tool requiere permisos especiales: {call.tool_name}",
                duration_ms=(time.time() - start_time) * 1000,
            ))

        # 3. Control de concurrencia
        if self._running_count >= self._config.max_concurrent:
            return Ok(ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                success=False,
                error="Maximo de ejecuciones concurrentes alcanzado",
                duration_ms=(time.time() - start_time) * 1000,
            ))

        # 4. Ejecutar con timeout
        self._running_count += 1
        try:
            result = await self._execute_with_timeout(call, spec)
            duration = (time.time() - start_time) * 1000

            if result.success:
                self._stats["total_success"] += 1
            else:
                self._stats["total_failed"] += 1

            result.duration_ms = duration

            # Registrar en registry stats
            self._registry.record_call(
                call.tool_name, duration,
                error=not result.success,
            )

            return Ok(result)

        except asyncio.TimeoutError:
            self._stats["total_timeout"] += 1
            duration = (time.time() - start_time) * 1000
            return Ok(ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                success=False,
                error=f"Timeout tras {spec.timeout_seconds}s",
                duration_ms=duration,
            ))
        finally:
            self._running_count -= 1

    async def execute_batch(
        self, calls: list[ToolCall]
    ) -> list[Result[ToolResult, Exception]]:
        """Ejecuta multiples tools en paralelo (respetando concurrencia)."""
        tasks = [self.execute(call) for call in calls]
        return await asyncio.gather(*tasks)

    # ─── Privados ─────────────────────────────────────────────

    async def _execute_with_timeout(
        self, call: ToolCall, spec: Any
    ) -> ToolResult:
        """Ejecuta una tool con timeout enforcement."""
        handler = self._registry.get_handler(call.tool_name)

        if handler is None:
            # Tool sin handler = simulacion
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                success=True,
                output=self._simulate_tool(call, spec),
                metadata={"simulated": True},
            )

        # Ejecutar handler con timeout
        timeout = spec.timeout_seconds or self._config.default_timeout
        try:
            output = await asyncio.wait_for(
                handler(call.arguments),
                timeout=timeout,
            )
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                success=True,
                output=output,
            )
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                success=False,
                error=str(e),
            )

    @staticmethod
    def _simulate_tool(call: ToolCall, spec: Any) -> str:
        """Simula la ejecucion de una tool sin handler."""
        return (
            f"[SIMULATED] {call.tool_name} ejecutada con argumentos: "
            f"{call.arguments}. Resultado simulado - no hay handler registrado."
        )

    @property
    def stats(self) -> dict[str, Any]:
        """Estadisticas del ejecutor."""
        return {
            **self._stats,
            "running_now": self._running_count,
            "max_concurrent": self._config.max_concurrent,
        }

    def create_call(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> ToolCall:
        """Factory para crear un ToolCall con ID generado."""
        return ToolCall(
            call_id=str(uuid.uuid4()),
            tool_name=tool_name,
            arguments=arguments,
        )
