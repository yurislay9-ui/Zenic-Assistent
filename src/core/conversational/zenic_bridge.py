"""
Bridge con el motor DAG Core.

Conecta el asistente con el orquestador DAG Core
para procesar solicitudes de codigo, automatizaciones
y razonamiento que requieren el motor completo.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

logger = logging.getLogger("zenic_agents.conversational.bridge")


class ZenicBridge:
    """
    Bridge entre el asistente y el motor DAG Core.

    Proporciona una interfaz limpia para invocar el motor
    desde la capa conversacional del asistente.

    Si el motor no esta disponible (ej: modo fallback),
    retorna respuestas degradadas apropiadas.
    """

    def __init__(self, orchestrator: Any = None) -> None:
        """
        Inicializa el bridge con un orquestador opcional.

        Args:
            orchestrator: Instancia de ZenicOrchestrator o DAGOrchestrator.
                          Si es None, el bridge funciona en modo fallback.
        """
        self._orchestrator = orchestrator
        self._available = orchestrator is not None
        self._call_count = 0
        self._error_count = 0
        self._total_latency_ms = 0.0

    @property
    def is_available(self) -> bool:
        """True si el motor DAG Core esta disponible."""
        return self._available and self._orchestrator is not None

    # ─── Ejecucion ────────────────────────────────────────────

    async def execute(self, message: str) -> dict[str, Any]:
        """
        Ejecuta un mensaje a traves del motor DAG Core.

        Args:
            message: Mensaje del usuario en lenguaje natural.

        Returns:
            Diccionario con resultado del motor, incluyendo:
            - status: SUCCESS, REJECTED, CACHED, ERROR, UNAVAILABLE
            - code: Codigo generado (si aplica)
            - error: Mensaje de error (si aplica)
            - route: Ruta tomada por el motor
            - processing_time_ms: Tiempo de procesamiento
            - explanations: Lista de explicaciones
        """
        if not self.is_available:
            return self._unavailable_response(message)

        start_time = time.time()
        self._call_count += 1

        try:
            # Ejecutar via el orquestador DAG Core
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._sync_execute,
                message,
            )

            elapsed_ms = (time.time() - start_time) * 1000
            self._total_latency_ms += elapsed_ms

            # Asegurar formato consistente
            if isinstance(result, dict):
                return self._normalize_result(result, elapsed_ms)
            return self._format_raw_result(result, elapsed_ms)

        except Exception as e:
            self._error_count += 1
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(f"Bridge error: {e}")
            return {
                "status": "ERROR",
                "code": "",
                "error": str(e),
                "processing_time_ms": elapsed_ms,
                "route": "",
                "explanations": [],
                "verdict": "",
            }

    def _sync_execute(self, message: str) -> Any:
        """Ejecucion sincrona del orquestador (se llama en executor)."""
        # Intentar metodo async primero
        if hasattr(self._orchestrator, 'execute'):
            import inspect
            if inspect.iscoroutinefunction(self._orchestrator.execute):
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(self._orchestrator.execute(message))
                finally:
                    loop.close()
            else:
                return self._orchestrator.execute(message)
        return None

    # ─── Formateo ─────────────────────────────────────────────

    @staticmethod
    def _normalize_result(result: dict, elapsed_ms: float) -> dict[str, Any]:
        """Normaliza el resultado del motor a formato estandar."""
        return {
            "status": result.get("status", "UNKNOWN"),
            "code": result.get("code", ""),
            "error": result.get("error", ""),
            "processing_time_ms": result.get("processing_time_ms", elapsed_ms),
            "route": result.get("route", ""),
            "criticality": result.get("criticality", ""),
            "explanations": result.get("explanations", []),
            "verdict": result.get("verdict", ""),
            "verdict_source": result.get("verdict_source", ""),
            "solver_status": result.get("solver_status", ""),
            "ast_analysis": result.get("ast_analysis", {}),
            "cache_source": result.get("cache_source", ""),
        }

    @staticmethod
    def _format_raw_result(result: Any, elapsed_ms: float) -> dict[str, Any]:
        """Formatea un resultado que no es diccionario."""
        if result is None:
            return {
                "status": "NO_OP",
                "code": "",
                "error": "Motor retorno None",
                "processing_time_ms": elapsed_ms,
                "route": "",
                "explanations": [],
            }
        return {
            "status": "SUCCESS",
            "code": str(result),
            "error": "",
            "processing_time_ms": elapsed_ms,
            "route": "raw",
            "explanations": [],
        }

    @staticmethod
    def _unavailable_response(message: str) -> dict[str, Any]:
        """Respuesta cuando el motor no esta disponible."""
        return {
            "status": "UNAVAILABLE",
            "code": "",
            "error": "Motor Zenic-Agents no disponible",
            "processing_time_ms": 0,
            "route": "fallback",
            "explanations": [
                "El motor no esta inicializado.",
                "Ejecutando en modo conversacional puro.",
            ],
            "verdict": "",
        }

    # ─── Estadisticas ─────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """Estadisticas del bridge."""
        avg_latency = (
            self._total_latency_ms / self._call_count
            if self._call_count > 0
            else 0.0
        )
        return {
            "available": self.is_available,
            "call_count": self._call_count,
            "error_count": self._error_count,
            "avg_latency_ms": round(avg_latency, 2),
            "total_latency_ms": round(self._total_latency_ms, 2),
        }

    def health_check(self) -> dict[str, Any]:
        """Verifica la salud del bridge y el motor."""
        health = {
            "bridge": "healthy" if self.is_available else "unavailable",
            "orchestrator_type": type(self._orchestrator).__name__ if self._orchestrator else "None",
        }
        if self._orchestrator and hasattr(self._orchestrator, '_health'):
            try:
                health["engine_health"] = self._orchestrator._health
            except Exception:
                health["engine_health"] = "unknown"
        return health
