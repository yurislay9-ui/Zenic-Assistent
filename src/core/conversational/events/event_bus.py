"""
Event Bus del Asistente.

Sistema de publicacion/suscripcion tipado para
desacoplar componentes. Los eventos se emiten
despues de que algo sucede, nunca antes.

Caracteristicas:
  - Suscripciones tipadas por EventType
  - Filtros por sesion o condicion custom
  - Prioridad de ejecucion
  - Async handlers soportados
  - Thread-safe
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from ...types.events import (
    Event, EventType, Subscription, EventHandler, AsyncEventHandler,
)

logger = logging.getLogger("zenic_agents.conversational.events")


class EventBus:
    """
    Bus de eventos del asistente.

    Los componentes emiten eventos y otros se suscriben.
    Desacopla completamente emisores de receptores.
    """

    def __init__(self) -> None:
        self._subscriptions: dict[EventType, list[Subscription]] = {}
        self._lock = threading.Lock()
        self._event_log: list[Event] = []
        self._max_log = 1000
        self._stats = {
            "total_emitted": 0,
            "total_handled": 0,
            "total_errors": 0,
        }

    # ─── Suscripcion ──────────────────────────────────────────

    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler | None = None,
        async_handler: AsyncEventHandler | None = None,
        filter_fn: Any = None,
        priority: int = 0,
    ) -> Subscription:
        """
        Suscribe un handler a un tipo de evento.

        Args:
            event_type: Tipo de evento a escuchar.
            handler: Callback sincrono.
            async_handler: Callback asincrono.
            filter_fn: Funcion de filtro (Event → bool).
            priority: Mayor = se ejecuta primero.

        Returns:
            Subscription para poder desuscribirse.
        """
        sub = Subscription(
            event_type=event_type,
            handler=handler,
            async_handler=async_handler,
            filter_fn=filter_fn,
            priority=priority,
        )

        with self._lock:
            if event_type not in self._subscriptions:
                self._subscriptions[event_type] = []
            self._subscriptions[event_type].append(sub)
            # Ordenar por prioridad descendente
            self._subscriptions[event_type].sort(
                key=lambda s: s.priority, reverse=True
            )

        logger.debug(
            f"Suscripcion: {event_type.value} "
            f"(priority={priority})"
        )
        return sub

    def unsubscribe(self, sub: Subscription) -> bool:
        """Desuscribe un handler."""
        with self._lock:
            subs = self._subscriptions.get(sub.event_type, [])
            try:
                subs.remove(sub)
                sub.active = False
                return True
            except ValueError:
                return False

    def unsubscribe_all(self, event_type: EventType | None = None) -> int:
        """Desuscribe todos los handlers de un tipo (o todos)."""
        with self._lock:
            if event_type:
                count = len(self._subscriptions.get(event_type, []))
                self._subscriptions[event_type] = []
                return count

            total = sum(
                len(subs) for subs in self._subscriptions.values()
            )
            self._subscriptions.clear()
            return total

    # ─── Emision ──────────────────────────────────────────────

    def emit(
        self,
        event_type: EventType,
        payload: dict[str, Any] | None = None,
        session_id: str = "",
        source: str = "",
        correlation_id: str = "",
    ) -> Event:
        """
        Emite un evento.

        Los handlers sincronos se ejecutan inmediatamente.
        Los handlers asincronos se programan en el event loop.
        """
        event = Event(
            event_type=event_type,
            session_id=session_id,
            payload=payload or {},
            source=source,
            correlation_id=correlation_id,
        )

        self._stats["total_emitted"] += 1

        # Log del evento
        self._log_event(event)

        # Ejecutar handlers
        with self._lock:
            subs = self._subscriptions.get(event_type, [])

        for sub in subs:
            if not sub.matches(event):
                continue

            try:
                # Handler sincrono
                if sub.handler:
                    sub.handler(event)
                    self._stats["total_handled"] += 1

                # Handler asincrono (programar en event loop)
                if sub.async_handler:
                    self._schedule_async(sub.async_handler, event)

            except Exception as e:
                self._stats["total_errors"] += 1
                logger.error(
                    f"Error en handler de {event_type.value}: {e}"
                )

        return event

    # ─── Query ────────────────────────────────────────────────

    def get_recent_events(
        self,
        event_type: EventType | None = None,
        count: int = 50,
    ) -> list[Event]:
        """Obtiene eventos recientes del log."""
        with self._lock:
            events = self._event_log
            if event_type:
                events = [e for e in events if e.event_type == event_type]
            return events[-count:]

    # ─── Stats ────────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """Estadisticas del event bus."""
        with self._lock:
            sub_counts = {
                et.value: len(subs)
                for et, subs in self._subscriptions.items()
            }
        return {
            **self._stats,
            "subscriptions": sub_counts,
            "log_size": len(self._event_log),
        }

    # ─── Privados ─────────────────────────────────────────────

    def _log_event(self, event: Event) -> None:
        """Almacena el evento en el log circular."""
        with self._lock:
            self._event_log.append(event)
            if len(self._event_log) > self._max_log:
                self._event_log = self._event_log[-self._max_log:]

    @staticmethod
    def _schedule_async(
        handler: AsyncEventHandler, event: Event
    ) -> None:
        """Programa un handler asincrono en el event loop."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(handler(event))
            else:
                loop.run_until_complete(handler(event))
        except RuntimeError:
            # No hay event loop, crear uno
            asyncio.run(handler(event))
