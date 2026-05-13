"""
Router principal del Asistente.

Decide a que pipeline enviar el mensaje basado en:
  - IntentCategory detectada
  - Disponibilidad del motor Zenic-Agents
  - Contexto de la sesion
  - Politicas de routing configurables

El router es determinista: misma entrada = misma ruta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ...types.base import Result, Ok, Err
from ...types.intent import AssistantIntent, IntentCategory

logger = logging.getLogger("zenic_agents.conversational.router")


# ─── Rutas disponibles ───────────────────────────────────────

class Pipeline(str, Enum):
    """Pipelines de procesamiento disponibles."""
    CONVERSATIONAL = "conversational"     # Chat general, sin motor
    CODE_ENGINE = "code_engine"           # Via motor Zenic-Agents
    QUESTION_ANSWER = "question_answer"   # Preguntas factuales
    COMMAND_HANDLER = "command_handler"   # Comandos directos
    CONFIG_HANDLER = "config_handler"     # Cambios de config
    TOOL_PIPELINE = "tool_pipeline"       # Tool execution
    FALLBACK = "fallback"                 # Cuando todo falla


# ─── Regla de routing ────────────────────────────────────────

@dataclass
class RouteRule:
    """Regla de routing: categoria → pipeline."""
    category: IntentCategory
    pipeline: Pipeline
    requires_engine: bool = False   # Necesita motor Zenic-Agents?
    priority: int = 0               # Mayor = se evalua primero
    condition: str = ""             # Condicion adicional (descriptive)


# ─── Reglas por defecto ──────────────────────────────────────

DEFAULT_RULES: list[RouteRule] = [
    # Comandos y config (alta prioridad, no necesitan engine)
    RouteRule(
        category=IntentCategory.COMMAND,
        pipeline=Pipeline.COMMAND_HANDLER,
        priority=100,
        condition="siempre se maneja localmente",
    ),
    RouteRule(
        category=IntentCategory.CONFIG,
        pipeline=Pipeline.CONFIG_HANDLER,
        priority=90,
        condition="siempre se maneja localmente",
    ),
    # Codigo (necesitan engine)
    RouteRule(
        category=IntentCategory.CODE_CREATE,
        pipeline=Pipeline.CODE_ENGINE,
        requires_engine=True,
        priority=80,
    ),
    RouteRule(
        category=IntentCategory.CODE_DEBUG,
        pipeline=Pipeline.CODE_ENGINE,
        requires_engine=True,
        priority=80,
    ),
    RouteRule(
        category=IntentCategory.CODE_REFACTOR,
        pipeline=Pipeline.CODE_ENGINE,
        requires_engine=True,
        priority=80,
    ),
    RouteRule(
        category=IntentCategory.CODE_OPTIMIZE,
        pipeline=Pipeline.CODE_ENGINE,
        requires_engine=True,
        priority=80,
    ),
    RouteRule(
        category=IntentCategory.CODE_ANALYZE,
        pipeline=Pipeline.CODE_ENGINE,
        requires_engine=True,
        priority=70,
    ),
    RouteRule(
        category=IntentCategory.CODE_EXPLAIN,
        pipeline=Pipeline.QUESTION_ANSWER,
        requires_engine=False,
        priority=70,
        condition="explicacion puede ser conversacional",
    ),
    # Preguntas
    RouteRule(
        category=IntentCategory.QUESTION,
        pipeline=Pipeline.QUESTION_ANSWER,
        priority=50,
    ),
    # Automatizacion y negocio
    RouteRule(
        category=IntentCategory.AUTOMATION,
        pipeline=Pipeline.CODE_ENGINE,
        requires_engine=True,
        priority=60,
    ),
    RouteRule(
        category=IntentCategory.BUSINESS,
        pipeline=Pipeline.CODE_ENGINE,
        requires_engine=True,
        priority=50,
    ),
    # Chat y feedback
    RouteRule(
        category=IntentCategory.CHAT,
        pipeline=Pipeline.CONVERSATIONAL,
        priority=30,
    ),
    RouteRule(
        category=IntentCategory.FEEDBACK,
        pipeline=Pipeline.CONVERSATIONAL,
        priority=30,
    ),
]


# ─── Resultado de routing ────────────────────────────────────

@dataclass
class RouteResult:
    """Resultado del proceso de routing."""
    pipeline: Pipeline = Pipeline.FALLBACK
    rule_used: RouteRule | None = None
    engine_available: bool = False
    engine_required: bool = False
    fallback_used: bool = False
    reason: str = ""
    alternative_pipelines: list[Pipeline] = field(default_factory=list)


# ─── Router ──────────────────────────────────────────────────

class AssistantRouter:
    """
    Router principal del asistente.

    Evalua reglas en orden de prioridad y selecciona
    el pipeline adecuado, con fallback automatico
    si el motor no esta disponible.
    """

    def __init__(
        self,
        rules: list[RouteRule] | None = None,
        engine_available: bool = False,
    ) -> None:
        self._rules = sorted(
            rules or DEFAULT_RULES,
            key=lambda r: r.priority,
            reverse=True,
        )
        self._engine_available = engine_available
        self._stats = {
            "total_routed": 0,
            "conversational": 0,
            "code_engine": 0,
            "fallbacks": 0,
        }

    def set_engine_available(self, available: bool) -> None:
        """Actualiza la disponibilidad del motor."""
        self._engine_available = available

    def route(self, intent: AssistantIntent) -> Result[RouteResult]:
        """
        Rutea una intencion al pipeline adecuado.

        Pipeline: eval rules → check engine → select → fallback if needed.
        """
        self._stats["total_routed"] += 1

        # Buscar regla matcheante
        matched_rule = self._find_rule(intent.category)

        if matched_rule is None:
            result = RouteResult(
                pipeline=Pipeline.CONVERSATIONAL,
                fallback_used=True,
                reason="Sin regla matcheante, fallback a conversacional",
            )
            self._stats["fallbacks"] += 1
            return Ok(result)

        # Verificar disponibilidad del engine
        pipeline = matched_rule.pipeline
        engine_required = matched_rule.requires_engine
        fallback_used = False

        if engine_required and not self._engine_available:
            # Fallback: code engine no disponible → conversacional
            pipeline = Pipeline.CONVERSATIONAL
            fallback_used = True
            logger.info(
                f"Engine no disponible. "
                f"Fallback: {matched_rule.pipeline.value} → {pipeline.value}"
            )
            self._stats["fallbacks"] += 1
        else:
            # Actualizar stat del pipeline seleccionado
            if pipeline == Pipeline.CODE_ENGINE:
                self._stats["code_engine"] += 1
            else:
                self._stats["conversational"] += 1

        # Buscar alternativas
        alternatives = self._find_alternatives(intent.category, pipeline)

        result = RouteResult(
            pipeline=pipeline,
            rule_used=matched_rule,
            engine_available=self._engine_available,
            engine_required=engine_required,
            fallback_used=fallback_used,
            reason=self._build_reason(matched_rule, fallback_used),
            alternative_pipelines=alternatives,
        )

        return Ok(result)

    # ─── Privados ─────────────────────────────────────────────

    def _find_rule(self, category: IntentCategory) -> RouteRule | None:
        """Busca la primera regla que matchea la categoria."""
        for rule in self._rules:
            if rule.category == category:
                return rule
        return None

    def _find_alternatives(
        self,
        category: IntentCategory,
        selected: Pipeline,
    ) -> list[Pipeline]:
        """Busca pipelines alternativos para la categoria."""
        alternatives: list[Pipeline] = []
        for rule in self._rules:
            if (
                rule.category == category
                and rule.pipeline != selected
            ):
                alternatives.append(rule.pipeline)
        # Siempre agregar fallback como alternativa
        if Pipeline.FALLBACK not in alternatives:
            alternatives.append(Pipeline.FALLBACK)
        return alternatives

    @staticmethod
    def _build_reason(rule: RouteRule, fallback: bool) -> str:
        """Construye la razon del routing."""
        parts = [f"Regla: {rule.category.value} → {rule.pipeline.value}"]
        if rule.condition:
            parts.append(f"Condicion: {rule.condition}")
        if fallback:
            parts.append("FALLBACK: engine no disponible")
        return " | ".join(parts)

    @property
    def stats(self) -> dict[str, Any]:
        """Estadisticas del router."""
        return {**self._stats, "engine_available": self._engine_available}
