"""
Gestor de sesiones del asistente.

Maneja el ciclo de vida de sesiones de conversacion:
creacion, activacion, limpieza y persistencia en memoria.
Thread-safe con locks por sesion.

Phase 3.3: Redis session store support for distributed sessions.
- Optional redis_url parameter enables dual-write to Redis
- Dual-read: Redis first, fall back to in-memory
- Dual-write: write to both Redis and in-memory
- restore_from_redis() recovers sessions after process restart
- Fully backward compatible — no Redis = existing behavior
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any, Dict, Optional

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
      - Dual-write/dual-read con Redis (si configurado)

    Phase 3.3: Redis Support
      - New optional ``redis_url`` parameter
      - If provided, creates RedisSessionStore as primary store
      - Dual-write: writes to both Redis and in-memory
      - Dual-read: reads from Redis first, falls back to in-memory
      - ``restore_from_redis()`` recovers sessions after restart
      - Fully backward compatible — no Redis = existing behavior
    """

    def __init__(
        self,
        max_sessions: int = MAX_SESSIONS,
        default_timeout: int = SESSION_TIMEOUT_SECONDS,
        redis_url: Optional[str] = None,
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

        # Phase 3.3: Redis session store
        self._redis_url = redis_url
        self._redis_store: Any = None
        self._redis_connected = False
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        if redis_url:
            self._init_redis_store(redis_url)

    def _init_redis_store(self, redis_url: str) -> None:
        """Initialize the Redis session store (lazy — connects on first use)."""
        try:
            from .redis_session_store import RedisSessionStore
            self._redis_store = RedisSessionStore(
                redis_url=redis_url,
                key_prefix="zenic:session",
                default_ttl=self._default_timeout,
            )
            logger.info(
                f"RedisSessionStore created for {redis_url} "
                f"(will connect on first async operation)"
            )
        except ImportError:
            logger.warning(
                "redis_session_store not available — "
                "running without Redis session persistence"
            )
            self._redis_store = None

    def _get_or_create_event_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create an event loop for async Redis operations."""
        if self._event_loop is not None and not self._event_loop.is_closed():
            return self._event_loop

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context — create a new loop in a thread
                import concurrent.futures
                self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                new_loop = asyncio.new_event_loop()
                self._event_loop = new_loop
                return new_loop
            self._event_loop = loop
            return loop
        except RuntimeError:
            loop = asyncio.new_event_loop()
            self._event_loop = loop
            return loop

    def _run_async(self, coro: Any) -> Any:
        """Run an async coroutine synchronously (for Redis operations)."""
        loop = self._get_or_create_event_loop()
        try:
            if loop.is_running():
                # We're inside an async context already — schedule in a thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result(timeout=10)
            return loop.run_until_complete(coro)
        except RuntimeError:
            # Loop might be closed, create a new one
            new_loop = asyncio.new_event_loop()
            self._event_loop = new_loop
            return new_loop.run_until_complete(coro)

    async def _ensure_redis_connected(self) -> bool:
        """Ensure Redis store is connected. Returns True if available."""
        if self._redis_store is None:
            return False
        if self._redis_connected and self._redis_store.is_redis_available:
            return True
        try:
            connected = await self._redis_store.connect()
            self._redis_connected = connected
            return connected
        except Exception as exc:
            logger.debug(f"Redis connection attempt failed: {exc}")
            self._redis_connected = False
            return False

    # ─── Redis Restore ────────────────────────────────────────

    async def restore_from_redis(self) -> int:
        """
        Recover sessions from Redis on startup.

        Reads all active sessions from Redis and loads them into
        the in-memory dict. This allows session continuity after
        a process restart.

        Returns:
            Number of sessions restored.
        """
        if self._redis_store is None:
            return 0

        if not await self._ensure_redis_connected():
            logger.warning("Redis unavailable — cannot restore sessions")
            return 0

        try:
            sessions = await self._redis_store.get_all_active()
            restored = 0
            with self._lock:
                for session in sessions:
                    if session.session_id not in self._sessions:
                        if len(self._sessions) < self._max_sessions:
                            self._sessions[session.session_id] = session
                            restored += 1

            if restored > 0:
                logger.info(
                    f"Restored {restored} sessions from Redis "
                    f"(total in-memory: {len(self._sessions)})"
                )
            return restored
        except Exception as exc:
            logger.warning(f"Failed to restore sessions from Redis: {exc}")
            return 0

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

            # Phase 3.3: Dual-write to Redis
            self._store_to_redis(session)

            return session

    def _store_to_redis(self, session: Session) -> None:
        """Store session to Redis (fire-and-forget, non-blocking)."""
        if self._redis_store is None:
            return
        try:
            self._run_async(self._async_store_to_redis(session))
        except Exception as exc:
            logger.debug(
                f"Redis store failed for session {session.session_id[:8]}... "
                f"({exc}) — in-memory only"
            )

    async def _async_store_to_redis(self, session: Session) -> None:
        """Async implementation of Redis store."""
        if await self._ensure_redis_connected():
            await self._redis_store.store(session)

    # ─── Recuperacion ─────────────────────────────────────────

    def get_session(self, session_id: SessionId) -> Optional[Session]:
        """Recupera una sesion por su ID. Retorna None si no existe.

        Phase 3.3: Dual-read pattern.
        Reads from in-memory first (fast path).
        Falls back to Redis if not found in memory.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                # Verificar expiracion
                if session.is_expired:
                    self._expire_session(session_id)
                    return None
                return session

        # Phase 3.3: Try Redis fallback
        redis_session = self._get_from_redis(session_id)
        if redis_session is not None:
            with self._lock:
                # Re-check under lock — another thread may have added it
                if session_id not in self._sessions:
                    self._sessions[session_id] = redis_session
                return redis_session

        return None

    def _get_from_redis(self, session_id: SessionId) -> Optional[Session]:
        """Try to get a session from Redis."""
        if self._redis_store is None:
            return None
        try:
            return self._run_async(self._async_get_from_redis(session_id))
        except Exception as exc:
            logger.debug(
                f"Redis get failed for session {session_id[:8]}... ({exc})"
            )
            return None

    async def _async_get_from_redis(self, session_id: SessionId) -> Optional[Session]:
        """Async implementation of Redis get."""
        if await self._ensure_redis_connected():
            return await self._redis_store.get(session_id)
        return None

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
        """Termina una sesion activa. Retorna True si existia.

        Phase 3.3: Also deletes from Redis.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.end()
            del self._sessions[session_id]
            self._stats["ended"] += 1
            logger.info(f"Sesion terminada: {session_id[:8]}...")

        # Phase 3.3: Also delete from Redis
        self._delete_from_redis(session_id)

        return True

    def _delete_from_redis(self, session_id: SessionId) -> None:
        """Delete session from Redis (fire-and-forget, non-blocking)."""
        if self._redis_store is None:
            return
        try:
            self._run_async(self._async_delete_from_redis(session_id))
        except Exception as exc:
            logger.debug(
                f"Redis delete failed for session {session_id[:8]}... ({exc})"
            )

    async def _async_delete_from_redis(self, session_id: SessionId) -> None:
        """Async implementation of Redis delete."""
        if await self._ensure_redis_connected():
            await self._redis_store.delete(session_id)

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

        # Phase 3.3: Update in Redis
        self._store_to_redis(session)

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

        # Phase 3.3: Update in Redis
        self._store_to_redis(session)

        return msg

    # ─── Limpieza ─────────────────────────────────────────────

    def cleanup_expired(self) -> int:
        """Limpia sesiones expiradas. Retorna cantidad eliminada.

        Phase 3.3: Also cleans up Redis expired sessions.
        """
        with self._lock:
            count = self._cleanup_expired()

        # Also clean up Redis
        if self._redis_store is not None:
            try:
                self._run_async(self._async_cleanup_redis())
            except Exception as exc:
                logger.debug(f"Redis cleanup failed: {exc}")

        return count

    async def _async_cleanup_redis(self) -> None:
        """Async Redis cleanup."""
        if await self._ensure_redis_connected():
            await self._redis_store.cleanup_expired()

    # ─── Estadisticas ─────────────────────────────────────────

    @property
    def stats(self) -> dict:
        """Estadisticas del gestor de sesiones."""
        with self._lock:
            active = sum(
                1 for s in self._sessions.values()
                if s.state == SessionState.ACTIVE
            )
            result = {
                **self._stats,
                "active_sessions": active,
                "total_sessions": len(self._sessions),
                "max_sessions": self._max_sessions,
            }

            # Phase 3.3: Include Redis store stats
            if self._redis_store is not None:
                result["redis_store"] = self._redis_store.get_stats()

            return result

    @property
    def active_count(self) -> int:
        """Cantidad de sesiones activas."""
        with self._lock:
            return len(self._sessions)

    @property
    def redis_available(self) -> bool:
        """Whether Redis session store is available."""
        return (
            self._redis_store is not None
            and self._redis_store.is_redis_available
        )

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

            # Also delete from Redis
            self._delete_from_redis(session_id)

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
