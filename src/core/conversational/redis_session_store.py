"""
Redis-backed session store for Zenic-Agents.

Stores sessions in Redis HASH keys with TTL-based expiry.
Falls back to an in-memory dict when Redis is unavailable,
ensuring graceful degradation.

Key layout:
    zenic:session:{session_id}  →  HASH with serialized session fields

Thread-safe via asyncio locks for concurrent async access.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from .types.session import (
    Message,
    MessageMetadata,
    MessageRole,
    Session,
    SessionConfig,
    SessionId,
    SessionState,
)

logger = logging.getLogger("zenic_agents.conversational.redis_session")

__all__ = ["RedisSessionStore"]


class RedisSessionStore:
    """
    Async Redis-backed session store with in-memory fallback.

    Features:
      - Stores sessions in Redis HASH ``zenic:session:{session_id}``
      - Sets TTL on each key matching the session's idle_timeout
      - Falls back to in-memory dict if Redis unavailable
      - Thread-safe with asyncio locks
      - Configurable key prefix and default TTL
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "zenic:session",
        default_ttl: int = 1800,
    ) -> None:
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._default_ttl = default_ttl

        # Redis client (initialized lazily)
        self._redis: Any = None
        self._redis_available: bool = False

        # In-memory fallback
        self._memory_store: Dict[SessionId, Dict[str, Any]] = {}

        # Asyncio lock for thread-safe access
        self._lock = asyncio.Lock()

    # ─── Redis Connection ────────────────────────────────────

    async def connect(self) -> bool:
        """
        Initialize the async Redis connection.

        Returns:
            True if Redis connected successfully, False otherwise.
        """
        try:
            import redis.asyncio as aioredis  # type: ignore[import-unresolved]

            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            await self._redis.ping()
            self._redis_available = True
            logger.info(
                f"RedisSessionStore connected to {self._redis_url}"
            )
            return True
        except ImportError:
            logger.warning(
                "redis.asyncio not available — using in-memory fallback"
            )
            self._redis_available = False
            return False
        except Exception as exc:
            logger.warning(
                f"Redis connection failed ({exc}) — using in-memory fallback"
            )
            self._redis_available = False
            return False

    async def close(self) -> None:
        """Close the Redis connection gracefully."""
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception as exc:
                logger.debug(f"Error closing Redis connection: {exc}")
            finally:
                self._redis = None
                self._redis_available = False

    @property
    def is_redis_available(self) -> bool:
        """Whether Redis is currently connected and available."""
        return self._redis_available and self._redis is not None

    # ─── Core Operations ─────────────────────────────────────

    async def store(self, session: Session) -> None:
        """
        Store a session in Redis and in-memory fallback.

        Serializes the Session dataclass to a JSON-compatible dict,
        stores it as a Redis HASH with TTL, and mirrors to memory.

        Args:
            session: The Session object to store.
        """
        data = self._serialize_session(session)
        ttl = session.config.idle_timeout_seconds or self._default_ttl

        async with self._lock:
            # Always store in-memory fallback
            self._memory_store[session.session_id] = data

            # Store in Redis if available
            if self.is_redis_available:
                try:
                    key = f"{self._key_prefix}:{session.session_id}"
                    await self._redis.hset(key, mapping=data)  # type: ignore[union-attr]
                    await self._redis.expire(key, ttl)  # type: ignore[union-attr]
                    logger.debug(
                        f"Session stored in Redis: {session.session_id[:8]}... "
                        f"(TTL={ttl}s)"
                    )
                except Exception as exc:
                    logger.warning(
                        f"Redis store failed for session {session.session_id[:8]}... "
                        f"({exc}) — data in memory only"
                    )
                    self._redis_available = False

    async def get(self, session_id: SessionId) -> Optional[Session]:
        """
        Retrieve a session by ID.

        Tries Redis first; falls back to in-memory if Redis fails
        or returns nothing.

        Args:
            session_id: The session identifier.

        Returns:
            The Session object, or None if not found.
        """
        async with self._lock:
            # Try Redis first
            if self.is_redis_available:
                try:
                    key = f"{self._key_prefix}:{session_id}"
                    data = await self._redis.hgetall(key)  # type: ignore[union-attr]
                    if data:
                        session = self._deserialize_session(data)
                        # Refresh TTL on access
                        ttl = session.config.idle_timeout_seconds or self._default_ttl
                        await self._redis.expire(key, ttl)  # type: ignore[union-attr]
                        # Sync to in-memory
                        self._memory_store[session_id] = self._serialize_session(session)
                        return session
                except Exception as exc:
                    logger.debug(
                        f"Redis get failed for session {session_id[:8]}... "
                        f"({exc}) — trying in-memory"
                    )
                    self._redis_available = False

            # Fall back to in-memory
            data = self._memory_store.get(session_id)
            if data:
                session = self._deserialize_session(data)
                # Check in-memory expiry
                if session.is_expired:
                    del self._memory_store[session_id]
                    return None
                return session

            return None

    async def delete(self, session_id: SessionId) -> bool:
        """
        Delete a session from both Redis and in-memory.

        Args:
            session_id: The session identifier.

        Returns:
            True if the session existed (in either store), False otherwise.
        """
        found = False
        async with self._lock:
            # Delete from in-memory
            if session_id in self._memory_store:
                del self._memory_store[session_id]
                found = True

            # Delete from Redis
            if self.is_redis_available:
                try:
                    key = f"{self._key_prefix}:{session_id}"
                    deleted = await self._redis.delete(key)  # type: ignore[union-attr]
                    if deleted:
                        found = True
                except Exception as exc:
                    logger.debug(
                        f"Redis delete failed for session {session_id[:8]}... "
                        f"({exc})"
                    )
                    self._redis_available = False

        return found

    async def get_all_active(self) -> List[Session]:
        """
        Get all active (non-expired) sessions.

        Scans Redis keys matching the prefix, falls back to
        in-memory store if Redis unavailable.

        Returns:
            List of active Session objects.
        """
        sessions: List[Session] = []

        async with self._lock:
            if self.is_redis_available:
                try:
                    pattern = f"{self._key_prefix}:*"
                    cursor = 0
                    while True:
                        cursor, keys = await self._redis.scan(  # type: ignore[union-attr]
                            cursor=cursor, match=pattern, count=100
                        )
                        for key in keys:
                            data = await self._redis.hgetall(key)  # type: ignore[union-attr]
                            if data:
                                try:
                                    session = self._deserialize_session(data)
                                    if not session.is_expired:
                                        sessions.append(session)
                                except Exception:
                                    pass
                        if cursor == 0:
                            break
                    return sessions
                except Exception as exc:
                    logger.debug(
                        f"Redis scan failed ({exc}) — using in-memory"
                    )
                    self._redis_available = False

            # Fallback: scan in-memory store
            expired_ids: List[SessionId] = []
            for sid, data in self._memory_store.items():
                try:
                    session = self._deserialize_session(data)
                    if session.is_expired:
                        expired_ids.append(sid)
                    else:
                        sessions.append(session)
                except Exception:
                    expired_ids.append(sid)

            # Clean up expired in-memory entries
            for sid in expired_ids:
                del self._memory_store[sid]

        return sessions

    async def cleanup_expired(self) -> int:
        """
        Clean up expired sessions from both stores.

        Redis TTL handles expiry automatically, but this also
        cleans the in-memory fallback.

        Returns:
            Number of expired sessions cleaned up.
        """
        cleaned = 0
        async with self._lock:
            expired_ids: List[SessionId] = []
            for sid, data in self._memory_store.items():
                try:
                    session = self._deserialize_session(data)
                    if session.is_expired:
                        expired_ids.append(sid)
                except Exception:
                    expired_ids.append(sid)

            for sid in expired_ids:
                del self._memory_store[sid]
                cleaned += 1

                # Also try deleting from Redis
                if self.is_redis_available:
                    try:
                        key = f"{self._key_prefix}:{sid}"
                        await self._redis.delete(key)  # type: ignore[union-attr]
                    except Exception:
                        self._redis_available = False

        if cleaned > 0:
            logger.debug(f"Cleaned up {cleaned} expired sessions")

        return cleaned

    # ─── Stats ───────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return store statistics."""
        return {
            "backend": "redis" if self.is_redis_available else "memory",
            "redis_url": self._redis_url if self.is_redis_available else "unavailable",
            "key_prefix": self._key_prefix,
            "default_ttl": self._default_ttl,
            "memory_store_count": len(self._memory_store),
        }

    # ─── Serialization ───────────────────────────────────────

    @staticmethod
    def _serialize_session(session: Session) -> Dict[str, Any]:
        """Serialize a Session dataclass to a flat dict for Redis HASH."""
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "state": session.state.value,
            "created_at": str(session.created_at),
            "last_activity": str(session.last_activity),
            "config": json.dumps({
                "max_history_messages": session.config.max_history_messages,
                "max_context_tokens": session.config.max_context_tokens,
                "idle_timeout_seconds": session.config.idle_timeout_seconds,
                "language": session.config.language,
                "tone": session.config.tone,
                "streaming_enabled": session.config.streaming_enabled,
                "tools_enabled": session.config.tools_enabled,
                "memory_enabled": session.config.memory_enabled,
                "personality_name": session.config.personality_name,
            }),
            "messages": json.dumps([
                RedisSessionStore._serialize_message(m)
                for m in session.messages
            ]),
            "metadata": json.dumps(session.metadata),
        }

    @staticmethod
    def _serialize_message(msg: Message) -> Dict[str, Any]:
        """Serialize a Message to a JSON-compatible dict."""
        return {
            "role": msg.role.value,
            "content": msg.content,
            "metadata": {
                "timestamp": msg.metadata.timestamp,
                "latency_ms": msg.metadata.latency_ms,
                "token_count": msg.metadata.token_count,
                "intent_category": msg.metadata.intent_category,
                "route_taken": msg.metadata.route_taken,
                "source": msg.metadata.source,
                "error": msg.metadata.error,
            },
            "tool_calls": msg.tool_calls,
            "tool_results": msg.tool_results,
        }

    @staticmethod
    def _deserialize_session(data: Dict[str, Any]) -> Session:
        """Deserialize a flat dict from Redis HASH back to a Session."""
        config_data = json.loads(data.get("config", "{}"))
        config = SessionConfig(
            max_history_messages=config_data.get("max_history_messages", 100),
            max_context_tokens=config_data.get("max_context_tokens", 4000),
            idle_timeout_seconds=config_data.get("idle_timeout_seconds", 1800),
            language=config_data.get("language", "es"),
            tone=config_data.get("tone", "professional"),
            streaming_enabled=config_data.get("streaming_enabled", True),
            tools_enabled=config_data.get("tools_enabled", True),
            memory_enabled=config_data.get("memory_enabled", True),
            personality_name=config_data.get("personality_name", "zenic"),
        )

        messages_data = json.loads(data.get("messages", "[]"))
        messages = [
            RedisSessionStore._deserialize_message(m)
            for m in messages_data
        ]

        metadata = json.loads(data.get("metadata", "{}"))

        return Session(
            session_id=data.get("session_id", ""),
            user_id=data.get("user_id", ""),
            state=SessionState(data.get("state", "active")),
            config=config,
            messages=messages,
            created_at=float(data.get("created_at", "0")),
            last_activity=float(data.get("last_activity", "0")),
            metadata=metadata,
        )

    @staticmethod
    def _deserialize_message(data: Dict[str, Any]) -> Message:
        """Deserialize a dict back to a Message."""
        meta_data = data.get("metadata", {})
        metadata = MessageMetadata(
            timestamp=meta_data.get("timestamp", 0.0),
            latency_ms=meta_data.get("latency_ms", 0.0),
            token_count=meta_data.get("token_count", 0),
            intent_category=meta_data.get("intent_category", ""),
            route_taken=meta_data.get("route_taken", ""),
            source=meta_data.get("source", "deterministic"),
            error=meta_data.get("error", ""),
        )

        return Message(
            role=MessageRole(data.get("role", "user")),
            content=data.get("content", ""),
            metadata=metadata,
            tool_calls=data.get("tool_calls", []),
            tool_results=data.get("tool_results", []),
        )
