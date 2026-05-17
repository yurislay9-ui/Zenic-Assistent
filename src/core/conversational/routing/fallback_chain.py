"""
Cadena de fallback del Asistente.

Cuando un pipeline falla o no esta disponible,
ejecuta una cadena de fallbacks ordenada por
prioridad hasta encontrar uno que funcione.

Garantiza que SIEMPRE hay una respuesta.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from ..types.base import Result, Ok, Err, PipelineContext
from ..types.response import AssistantResponse, ResponseFormat, ResponseMetadata
from .router import Pipeline

logger = logging.getLogger("zenic_agents.conversational.fallback")


# ─── Fallback handler ────────────────────────────────────────

FallbackHandler = Callable[[PipelineContext], Awaitable[Result[AssistantResponse, Exception]]]


@dataclass
class FallbackEntry:
    """Entrada en la cadena de fallback."""
    pipeline: Pipeline
    handler: FallbackHandler | None = None
    priority: int = 0             # Mayor = se intenta primero
    description: str = ""


# ─── Cadena de fallback ──────────────────────────────────────

class FallbackChain:
    """
    Cadena de fallback para garantizar respuestas.

    Siempre hay un fallback terminal que retorna una
    respuesta generica. Nunca se lanza una excepcion.
    """

    def __init__(self) -> None:
        self._entries: list[FallbackEntry] = []
        self._stats = {
            "total_fallbacks": 0,
            "successful_fallbacks": 0,
            "terminal_fallbacks": 0,
        }

    def register(self, entry: FallbackEntry) -> None:
        """Registra un fallback handler."""
        self._entries.append(entry)
        self._entries.sort(key=lambda e: e.priority, reverse=True)

    async def execute(
        self,
        ctx: PipelineContext,
        failed_pipeline: Pipeline | None = None,
    ) -> Result[AssistantResponse, Exception]:
        """
        Ejecuta la cadena de fallback.

        Intenta cada handler en orden de prioridad hasta
        que uno retorna Ok. Si todos fallan, retorna
        una respuesta generica (terminal fallback).
        """
        self._stats["total_fallbacks"] += 1
        start_time = time.time()

        logger.info(
            f"Fallback chain activada "
            f"(pipeline fallido: {failed_pipeline.value if failed_pipeline else 'none'})"
        )

        # Intentar cada fallback registrado
        for entry in self._entries:
            if entry.handler is None:
                continue

            try:
                result = await entry.handler(ctx)
                if result.is_ok:
                    elapsed = (time.time() - start_time) * 1000
                    self._stats["successful_fallbacks"] += 1
                    logger.info(
                        f"Fallback exitoso: {entry.pipeline.value} "
                        f"({elapsed:.0f}ms)"
                    )
                    return result
            except Exception as e:
                logger.warning(
                    f"Fallback {entry.pipeline.value} fallo: {e}"
                )
                continue

        # Terminal fallback: respuesta generica garantizada
        self._stats["terminal_fallbacks"] += 1
        return Ok(self._terminal_fallback(ctx))

    @staticmethod
    def _terminal_fallback(ctx: PipelineContext) -> AssistantResponse:
        """Fallback terminal: siempre produce una respuesta."""
        lang = ctx.metadata.get("language", "es")

        if lang == "en":
            content = (
                "I'm having trouble processing your request right now. "
                "Please try again in a moment or rephrase your question."
            )
        else:
            content = (
                "Estoy teniendo dificultades para procesar tu solicitud "
                "en este momento. Por favor, intenta de nuevo en un "
                "momento o reformula tu pregunta."
            )

        return AssistantResponse(
            content=content,
            format=ResponseFormat.MARKDOWN,
            metadata=ResponseMetadata(
                source="fallback_terminal",
                route_taken="fallback_chain",
            ),
        )

    @property
    def stats(self) -> dict[str, Any]:
        """Estadisticas del fallback chain."""
        return {**self._stats, "registered_handlers": len(self._entries)}
