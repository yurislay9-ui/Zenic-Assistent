"""
Conocimiento base del motor de conversacion.

Carga conocimiento predefinido del asistente al
KnowledgeBase durante la inicializacion.
"""

from __future__ import annotations

import logging
from typing import Any

from .knowledge import KnowledgeBase

logger = logging.getLogger("zenic_agents.conversational.engine_knowledge")


def load_builtin_knowledge(kb: KnowledgeBase) -> None:
    """Carga conocimiento base del asistente en la KnowledgeBase."""
    concepts: list[tuple[str, str, str, list[str]]] = [
        (
            "Arquitectura Zenic-Agents",
            "Zenic-Agents es un motor de IA quirurgico con 48 agentes especializados "
            "organizados en capas. El asistente usa un sistema determinista con "
            "fallbacks y la IA solo como arbitro binario.",
            "architecture",
            ["zenic", "arquitectura", "agentes", "motor"],
        ),
        (
            "Sistema de Memoria",
            "El asistente tiene 3 niveles de memoria: Working (contexto inmediato), "
            "Short-Term (datos de sesion) y Long-Term (persistente entre sesiones). "
            "Las memorias se promueven automaticamente segun su importancia.",
            "architecture",
            ["memoria", "working", "short-term", "long-term"],
        ),
        (
            "Sistema de Herramientas",
            "El asistente puede ejecutar herramientas: busqueda web, calculadora, "
            "ejecucion de codigo en sandbox, lectura de archivos y busqueda en memoria. "
            "Cada herramienta tiene permisos configurables.",
            "architecture",
            ["herramientas", "tools", "web search", "calculator"],
        ),
        (
            "Clasificacion de Intencion",
            "El sistema clasifica mensajes en 13 categorias de intencion usando "
            "un motor multi-capa: keywords, patterns, contexto y calibracion. "
            "Las categorias incluyen chat, preguntas, comandos, config y 6 tipos de codigo.",
            "architecture",
            ["intencion", "clasificacion", "intent", "categorias"],
        ),
        (
            "Python Best Practices",
            "Usa type hints, dataclasses, Protocol para DI, Result monad para errores. "
            "Archivos max 400 lineas, modulos con __init__.py, imports absolutos. "
            "Thread-safe con locks, async para I/O.",
            "programming",
            ["python", "best practices", "type hints", "dataclasses"],
        ),
    ]

    for title, content, category, keywords in concepts:
        kb.store_concept(
            title=title,
            content=content,
            category=category,
            tags=keywords,
            keywords=keywords,
        )

    logger.info(f"Conocimiento base cargado: {len(concepts)} entradas")
