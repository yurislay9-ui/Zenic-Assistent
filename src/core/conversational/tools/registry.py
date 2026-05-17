"""
Registro de herramientas del Asistente.

Mantiene el catalogo de tools disponibles con sus
specs, handlers y estado. Permite registro dinamico
y busqueda por nombre o categoria.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Awaitable

from ..types.tool_use import ToolSpec, ToolPermission, BUILTIN_TOOLS

logger = logging.getLogger("zenic_agents.conversational.tools.registry")

# ─── Handler de tool ─────────────────────────────────────────

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]


# ─── Entry de registro ───────────────────────────────────────

class _ToolEntry:
    """Entrada interna del registro."""
    __slots__ = ("spec", "handler", "call_count", "error_count", "total_ms")

    def __init__(self, spec: ToolSpec, handler: ToolHandler | None = None) -> None:
        self.spec = spec
        self.handler = handler
        self.call_count: int = 0
        self.error_count: int = 0
        self.total_ms: float = 0.0


class ToolRegistry:
    """
    Registro de herramientas disponibles.

    Permite:
      - Registrar tools con specs y handlers
      - Buscar por nombre o categoria
      - Listar tools disponibles para OpenAI format
      - Track de uso y errores
    """

    def __init__(self) -> None:
        self._tools: dict[str, _ToolEntry] = {}
        self._category_index: dict[str, list[str]] = {}
        self._lock = threading.Lock()

        # Cargar tools integradas
        self._load_builtins()

    # ─── Registro ─────────────────────────────────────────────

    def register(
        self,
        spec: ToolSpec,
        handler: ToolHandler | None = None,
    ) -> bool:
        """
        Registra una herramienta.

        Returns:
            True si se registro, False si ya existia y no se sobreescribio.
        """
        with self._lock:
            if spec.name in self._tools and spec.enabled:
                return False  # No sobreescribir

            self._tools[spec.name] = _ToolEntry(spec, handler)

            # Indexar por categoria
            cat = spec.category
            if cat not in self._category_index:
                self._category_index[cat] = []
            if spec.name not in self._category_index[cat]:
                self._category_index[cat].append(spec.name)

            logger.info(f"Tool registrada: {spec.name} (cat={spec.category})")
            return True

    def unregister(self, name: str) -> bool:
        """Desregistra una herramienta."""
        with self._lock:
            entry = self._tools.pop(name, None)
            if entry is None:
                return False

            # Limpiar indice
            cat = entry.spec.category
            if cat in self._category_index:
                self._category_index[cat] = [
                    n for n in self._category_index[cat] if n != name
                ]
            return True

    # ─── Lectura ──────────────────────────────────────────────

    def get(self, name: str) -> ToolSpec | None:
        """Obtiene la spec de una herramienta."""
        with self._lock:
            entry = self._tools.get(name)
            return entry.spec if entry else None

    def get_handler(self, name: str) -> ToolHandler | None:
        """Obtiene el handler de una herramienta."""
        with self._lock:
            entry = self._tools.get(name)
            return entry.handler if entry else None

    def is_registered(self, name: str) -> bool:
        """Verifica si una herramienta esta registrada."""
        return name in self._tools

    def is_enabled(self, name: str) -> bool:
        """Verifica si una herramienta esta habilitada."""
        with self._lock:
            entry = self._tools.get(name)
            return entry.spec.enabled if entry else False

    def list_tools(self, category: str | None = None) -> list[ToolSpec]:
        """Lista las specs de herramientas disponibles."""
        with self._lock:
            if category:
                names = self._category_index.get(category, [])
                return [
                    self._tools[n].spec
                    for n in names
                    if n in self._tools and self._tools[n].spec.enabled
                ]
            return [
                e.spec for e in self._tools.values()
                if e.spec.enabled
            ]

    def list_openai_format(self) -> list[dict[str, Any]]:
        """Lista tools en formato OpenAI function calling."""
        return [t.to_openai_format() for t in self.list_tools()]

    # ─── Stats ────────────────────────────────────────────────

    def record_call(self, name: str, duration_ms: float, error: bool = False) -> None:
        """Registra una llamada a tool para estadisticas."""
        with self._lock:
            entry = self._tools.get(name)
            if entry:
                entry.call_count += 1
                entry.total_ms += duration_ms
                if error:
                    entry.error_count += 1

    @property
    def stats(self) -> dict[str, Any]:
        """Estadisticas del registro."""
        with self._lock:
            return {
                "total_tools": len(self._tools),
                "enabled_tools": sum(
                    1 for e in self._tools.values() if e.spec.enabled
                ),
                "categories": list(self._category_index.keys()),
                "tools": {
                    name: {
                        "calls": entry.call_count,
                        "errors": entry.error_count,
                        "avg_ms": (
                            entry.total_ms / entry.call_count
                            if entry.call_count > 0 else 0.0
                        ),
                    }
                    for name, entry in self._tools.items()
                },
            }

    # ─── Privados ─────────────────────────────────────────────

    def _load_builtins(self) -> None:
        """Carga las tools integradas."""
        for spec in BUILTIN_TOOLS:
            self._tools[spec.name] = _ToolEntry(spec)
            cat = spec.category
            if cat not in self._category_index:
                self._category_index[cat] = []
            self._category_index[cat].append(spec.name)

        logger.info(f"Built-in tools cargadas: {len(BUILTIN_TOOLS)}")
