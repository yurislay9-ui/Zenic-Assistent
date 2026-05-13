"""
Gestor de sesiones del asistente.

Maneja el ciclo de vida de sesiones de conversacion:
creacion, activacion, limpieza y persistencia en memoria.
Thread-safe con locks por sesion.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from .types.session import (
    Session, SessionId, SessionState, SessionConfig,
    Message, MessageRole, new_session_id,
)
from .config.constants import (
    SESSION_TIMEOUT_SECONDS,
    MAX_SESSIONS,
    MAX_MESSAGES_PER_SESSION,
)

logger = logging.getLogger("zenic_agents.conversational.session")


class SessionManager:
    """
    Gestiona sesiones de conversacion.

    Responsabilidades:
      - Crear sesiones nuevas con configuracion
      - Recuperar sesiones existentes
      - Limpiar sesiones expiradas
      - Mantener limite de sesiones activas
      - Thread-safe para acceso concurrente
    """

    def __init__(
        self,
        max_sessions: int = MAX_SESSIONS,
        default_timeout: int = SESSION_TIMEOUT_SECONDS,
    ) -> None:
        self._sessions: dict[SessionId, Session] = {}
        self._lock = threading.RLock()
        self._max_sessions = max_sessions
        self._default_timeout = default_timeout
        self._stats = {
            "created": 0,
            "ended": 0,
            "expired": 0,
            "rejected_max": 0,
        }

    # ─── Creacion ─────────────────────────────────────────────

    def create_session(
        self,
        user_id: str = "",
        config: Optional[SessionConfig] = None,
    ) -> Session:
        """
        Crea una nueva sesion de conversacion.

        Args:
            user_id: Identificador del usuario (opcional).
            config: Configuracion de sesion (usa defaults si no se provee).

        Returns:
            Nueva sesion activa.

        Raises:
            RuntimeError: Si se alcanzo el limite de sesiones.
        """
        with self._lock:
            # Limpiar expiradas antes de verificar limite
            self._cleanup_expired()

            if len(self._sessions) >= self._max_sessions:
                self._stats["rejected_max"] += 1
                raise RuntimeError(
                    f"Maximo de sesiones alcanzado ({self._max_sessions})"
                )

            session_config = config or SessionConfig(
                idle_timeout_seconds=self._default_timeout,
                max_history_messages=MAX_MESSAGES_PER_SESSION,
            )

            session = Session(
                user_id=user_id,
                config=session_config,
            )

            # Agregar mensaje de sistema inicial
            system_msg = Message(
                role=MessageRole.SYSTEM,
                content=self._build_system_message(session),
            )
            session.add_message(system_msg)

            self._sessions[session.session_id] = session
            self._stats["created"] += 1
            logger.info(
                f"Sesion creada: {session.session_id[:8]}... "
                f"(user={user_id or 'anon'}, total={len(self._sessions)})"
            )
            return session

    # ─── Recuperacion ─────────────────────────────────────────

    def get_session(self, session_id: SessionId) -> Optional[Session]:
        """Recupera una sesion por su ID. Retorna None si no existe."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None

            # Verificar expiracion
            if session.is_expired:
                self._expire_session(session_id)
                return None

            return session

    def get_or_create(
        self,
        session_id: Optional[SessionId] = None,
        user_id: str = "",
    ) -> Session:
        """Recupera una sesion existente o crea una nueva."""
        if session_id:
            session = self.get_session(session_id)
            if session:
                return session
        return self.create_session(user_id=user_id)

    # ─── Terminacion ──────────────────────────────────────────

    def end_session(self, session_id: SessionId) -> bool:
        """Termina una sesion activa. Retorna True si existia."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.end()
            del self._sessions[session_id]
            self._stats["ended"] += 1
            logger.info(f"Sesion terminada: {session_id[:8]}...")
            return True

    # ─── Mensajes ─────────────────────────────────────────────

    def add_user_message(
        self, session_id: SessionId, content: str
    ) -> Optional[Message]:
        """Agrega un mensaje de usuario a una sesion."""
        session = self.get_session(session_id)
        if session is None:
            return None

        msg = Message(
            role=MessageRole.USER,
            content=content,
        )
        session.add_message(msg)
        return msg

    def add_assistant_message(
        self, session_id: SessionId, content: str, metadata: Optional[dict] = None
    ) -> Optional[Message]:
        """Agrega un mensaje del asistente a una sesion."""
        session = self.get_session(session_id)
        if session is None:
            return None

        from .types.session import MessageMetadata
        msg_metadata = MessageMetadata()
        if metadata:
            for k, v in metadata.items():
                if hasattr(msg_metadata, k):
                    setattr(msg_metadata, k, v)

        msg = Message(
            role=MessageRole.ASSISTANT,
            content=content,
            metadata=msg_metadata,
        )
        session.add_message(msg)
        return msg

    # ─── Limpieza ─────────────────────────────────────────────

    def cleanup_expired(self) -> int:
        """Limpia sesiones expiradas. Retorna cantidad eliminada."""
        with self._lock:
            return self._cleanup_expired()

    # ─── Estadisticas ─────────────────────────────────────────

    @property
    def stats(self) -> dict:
        """Estadisticas del gestor de sesiones."""
        with self._lock:
            active = sum(
                1 for s in self._sessions.values()
                if s.state == SessionState.ACTIVE
            )
            return {
                **self._stats,
                "active_sessions": active,
                "total_sessions": len(self._sessions),
                "max_sessions": self._max_sessions,
            }

    @property
    def active_count(self) -> int:
        """Cantidad de sesiones activas."""
        with self._lock:
            return len(self._sessions)

    # ─── Privados ─────────────────────────────────────────────

    def _cleanup_expired(self) -> int:
        """Elimina sesiones expiradas (debe llamarse con lock)."""
        expired_ids = [
            sid for sid, session in self._sessions.items()
            if session.is_expired
        ]
        for sid in expired_ids:
            self._expire_session(sid)
        return len(expired_ids)

    def _expire_session(self, session_id: SessionId) -> None:
        """Marca y elimina una sesion expirada (debe llamarse con lock)."""
        session = self._sessions.pop(session_id, None)
        if session:
            session.state = SessionState.ENDED
            self._stats["expired"] += 1
            logger.debug(f"Sesion expirada: {session_id[:8]}...")

    @staticmethod
    def _build_system_message(session: Session) -> str:
        """Genera el mensaje de sistema inicial para una sesion."""
        lang = session.config.language
        if lang == "es":
            return (
                "Eres Zenic-Agents Asistente, un asistente inteligente "
                "basado en un motor de IA quirurgico con 48 agentes especializados. "
                "Puedes ayudar con codigo, razonamiento, automatizaciones y mas. "
                "Responde siempre en espanol de forma clara y util."
            )
        else:
            return (
                "You are Zenic-Agents Assistant, an intelligent assistant "
                "based on a surgical AI engine with 48 specialized agents. "
                "You can help with code, reasoning, automations and more. "
                "Always respond clearly and helpfully."
            )
