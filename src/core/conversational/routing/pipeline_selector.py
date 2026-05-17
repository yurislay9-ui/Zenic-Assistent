"""
Selector de pipeline del Asistente.

Construye y gestiona los pipelines de procesamiento.
Cada pipeline es una secuencia de procesadores
que transforma el contexto paso a paso.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..types.base import Result, Ok, Err, PipelineContext
from .router import Pipeline

logger = logging.getLogger("zenic_agents.conversational.pipeline")


# ─── Protocolo de step ───────────────────────────────────────

@runtime_checkable
class PipelineStep(Protocol):
    """Un paso dentro de un pipeline de procesamiento."""

    @property
    def name(self) -> str:
        ...

    async def execute(self, ctx: PipelineContext) -> Result[PipelineContext, Exception]:
        ...


# ─── Pipeline ejecutable ─────────────────────────────────────

@dataclass
class PipelineDefinition:
    """Definicion de un pipeline con sus steps."""
    name: str = ""
    pipeline_type: Pipeline = Pipeline.CONVERSATIONAL
    steps: list[PipelineStep] = field(default_factory=list)
    timeout_ms: float = 30000.0     # Timeout total del pipeline
    retry_count: int = 0            # Retries en caso de error

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def step_names(self) -> list[str]:
        return [s.name for s in self.steps]


# ─── Resultado de ejecucion ──────────────────────────────────

@dataclass
class PipelineResult:
    """Resultado de ejecutar un pipeline."""
    success: bool = False
    pipeline_name: str = ""
    steps_executed: int = 0
    total_steps: int = 0
    execution_time_ms: float = 0.0
    context: PipelineContext = field(default_factory=PipelineContext)
    errors: list[str] = field(default_factory=list)
    step_timings: dict[str, float] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        return self.steps_executed == self.total_steps and self.success


# ─── Pipeline Selector ───────────────────────────────────────

class PipelineSelector:
    """
    Selecciona y ejecuta el pipeline adecuado.

    Mantiene un registro de pipelines disponibles y los
    ejecuta secuencialmente con medicion de tiempos.
    """

    def __init__(self) -> None:
        self._pipelines: dict[Pipeline, PipelineDefinition] = {}
        self._execution_stats: dict[str, dict[str, Any]] = {}

    def register(self, definition: PipelineDefinition) -> None:
        """Registra un pipeline."""
        self._pipelines[definition.pipeline_type] = definition
        logger.info(
            f"Pipeline registrado: {definition.name} "
            f"({definition.step_count} steps)"
        )

    async def execute(
        self,
        pipeline_type: Pipeline,
        ctx: PipelineContext,
    ) -> Result[PipelineResult, Exception]:
        """
        Ejecuta un pipeline completo.

        Pipeline: validate → execute steps → collect result → stats.
        """
        start_time = time.time()
        pipeline = self._pipelines.get(pipeline_type)

        if pipeline is None:
            return Err(ValueError(
                f"Pipeline no registrado: {pipeline_type.value}"
            ))

        result = PipelineResult(
            pipeline_name=pipeline.name,
            total_steps=pipeline.step_count,
            context=ctx,
        )

        # Ejecutar steps secuencialmente
        current_ctx = ctx
        for step in pipeline.steps:
            step_start = time.time()
            try:
                step_result = await step.execute(current_ctx)
                step_time = (time.time() - step_start) * 1000

                if step_result.is_ok:
                    current_ctx = step_result.unwrap
                    result.steps_executed += 1
                    result.step_timings[step.name] = step_time
                else:
                    result.errors.append(
                        f"Step '{step.name}' fallo: {step_result.error}"
                    )
                    # Continuar con contexto parcial
                    result.step_timings[step.name] = step_time
                    break

            except Exception as e:
                step_time = (time.time() - step_start) * 1000
                result.errors.append(f"Step '{step.name}' excepcion: {e}")
                result.step_timings[step.name] = step_time
                break

        result.success = result.steps_executed == result.total_steps
        result.context = current_ctx
        result.execution_time_ms = (time.time() - start_time) * 1000

        # Actualizar stats
        self._update_stats(result)

        return Ok(result)

    def get_pipeline(self, pipeline_type: Pipeline) -> PipelineDefinition | None:
        """Obtiene la definicion de un pipeline."""
        return self._pipelines.get(pipeline_type)

    def list_pipelines(self) -> list[str]:
        """Lista los nombres de pipelines registrados."""
        return [p.name for p in self._pipelines.values()]

    @property
    def stats(self) -> dict[str, Any]:
        """Estadisticas de ejecucion."""
        return self._execution_stats

    def _update_stats(self, result: PipelineResult) -> None:
        """Actualiza estadisticas de ejecucion."""
        name = result.pipeline_name
        if name not in self._execution_stats:
            self._execution_stats[name] = {
                "total": 0,
                "success": 0,
                "failures": 0,
                "avg_time_ms": 0.0,
            }

        stats = self._execution_stats[name]
        stats["total"] += 1
        if result.success:
            stats["success"] += 1
        else:
            stats["failures"] += 1

        # Promedio movil del tiempo
        prev_avg = stats["avg_time_ms"]
        count = stats["total"]
        stats["avg_time_ms"] = (
            prev_avg * (count - 1) + result.execution_time_ms
        ) / count
