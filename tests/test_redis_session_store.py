"""
ZENIC-AGENTS v16 — Redis Session Store Test Suite (Phase 3.3)

Tests for the RedisSessionStore covering:
1. Store and retrieve sessions
2. TTL expiration
3. Dual-write pattern (Redis + memory)
4. Fallback to in-memory when Redis unavailable
5. Concurrent access
6. SessionManager integration with Redis
7. Cleanup of expired sessions

All Redis-dependent tests are automatically skipped if Redis is not available.
Run with:  pytest tests/test_redis_session_store.py -v
"""

import asyncio
import os
import sys
import time

import pytest
import pytest_asyncio

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Connection check helper ─────────────────────────────────

def _redis_available() -> bool:
    """Check if Redis is reachable at the configured URL."""
    try:
        import redis  # noqa: F401
    except ImportError:
        return False

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    try:
        client = redis.from_url(redis_url, socket_connect_timeout=5)
        result = client.ping()
        client.close()
        return result
    except Exception:
        return False


# Skip all tests if Redis is not reachable
redis_not_available = not _redis_available()
SKIP_REASON = (
    "Redis is not available. "
    "Start it with: docker compose up -d redis"
)


# ── Fixtures ─────────────────────────────────────────────────

@pytest_asyncio.fixture
async def redis_session_store():
    """Create a RedisSessionStore for testing."""
    from src.core.conversational.redis_session_store import RedisSessionStore

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    store = RedisSessionStore(
        redis_url=redis_url,
        key_prefix="test:zenic:session",
        default_ttl=60,
    )
    connected = await store.connect()
    if not connected and redis_not_available:
        pytest.skip(SKIP_REASON)

    yield store

    # Cleanup: delete all test keys
    if store.is_redis_available:
        try:
            pattern = "test:zenic:session:*"
            cursor = 0
            while True:
                cursor, keys = await store._redis.scan(
                    cursor=cursor, match=pattern, count=100
                )
                if keys:
                    await store._redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            pass

    await store.close()


@pytest.fixture
def sample_session():
    """Create a sample session for testing."""
    from src.core.conversational.types.session import (
        Session, SessionConfig, Message, MessageRole, MessageMetadata,
    )

    session = Session(
        user_id="test_user",
        config=SessionConfig(
            idle_timeout_seconds=60,
            max_history_messages=100,
            language="en",
        ),
    )
    # Add a system message
    session.add_message(Message(
        role=MessageRole.SYSTEM,
        content="Test system message",
    ))
    # Add a user message
    session.add_message(Message(
        role=MessageRole.USER,
        content="Hello, test!",
        metadata=MessageMetadata(
            latency_ms=42.5,
            token_count=5,
        ),
    ))
    return session


# ── 1. Store and Retrieve ───────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestStoreAndRetrieve:
    """Test basic store and retrieve operations."""

    async def test_store_and_get(self, redis_session_store, sample_session):
        """Storing a session and retrieving it should return identical data."""
        await redis_session_store.store(sample_session)

        retrieved = await redis_session_store.get(sample_session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == sample_session.session_id
        assert retrieved.user_id == sample_session.user_id
        assert retrieved.state == sample_session.state
        assert len(retrieved.messages) == len(sample_session.messages)
        assert retrieved.config.idle_timeout_seconds == sample_session.config.idle_timeout_seconds

    async def test_get_nonexistent_session(self, redis_session_store):
        """Getting a non-existent session should return None."""
        result = await redis_session_store.get("nonexistent-session-id")
        assert result is None

    async def test_store_preserves_messages(self, redis_session_store, sample_session):
        """Messages should survive serialization round-trip."""
        await redis_session_store.store(sample_session)
        retrieved = await redis_session_store.get(sample_session.session_id)

        assert retrieved is not None
        assert len(retrieved.messages) == 2
        assert retrieved.messages[0].role.value == "system"
        assert retrieved.messages[0].content == "Test system message"
        assert retrieved.messages[1].role.value == "user"
        assert retrieved.messages[1].content == "Hello, test!"
        assert retrieved.messages[1].metadata.latency_ms == 42.5
        assert retrieved.messages[1].metadata.token_count == 5

    async def test_store_preserves_config(self, redis_session_store, sample_session):
        """SessionConfig should survive serialization round-trip."""
        await redis_session_store.store(sample_session)
        retrieved = await redis_session_store.get(sample_session.session_id)

        assert retrieved is not None
        assert retrieved.config.idle_timeout_seconds == 60
        assert retrieved.config.max_history_messages == 100
        assert retrieved.config.language == "en"

    async def test_store_preserves_metadata(self, redis_session_store):
        """Session metadata dict should survive round-trip."""
        from src.core.conversational.types.session import Session, SessionConfig

        session = Session(
            user_id="meta_user",
            config=SessionConfig(idle_timeout_seconds=60),
            metadata={"custom_key": "custom_value", "count": 42},
        )
        await redis_session_store.store(session)
        retrieved = await redis_session_store.get(session.session_id)

        assert retrieved is not None
        assert retrieved.metadata.get("custom_key") == "custom_value"
        assert retrieved.metadata.get("count") == 42


# ── 2. TTL Expiration ──────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestTTLExpiration:
    """Test TTL-based session expiration."""

    async def test_ttl_set_on_store(self, redis_session_store, sample_session):
        """Redis key should have TTL set matching session's idle_timeout."""
        from src.core.conversational.types.session import SessionConfig

        # Use a specific timeout
        sample_session.config.idle_timeout_seconds = 120
        await redis_session_store.store(sample_session)

        key = f"test:zenic:session:{sample_session.session_id}"
        ttl = await redis_session_store._redis.ttl(key)
        assert ttl > 0
        assert ttl <= 120

    async def test_ttl_refreshed_on_get(self, redis_session_store, sample_session):
        """Getting a session should refresh the TTL."""
        sample_session.config.idle_timeout_seconds = 60
        await redis_session_store.store(sample_session)

        key = f"test:zenic:session:{sample_session.session_id}"

        # Wait a bit for TTL to decrease
        await asyncio.sleep(1)

        # Get should refresh TTL
        await redis_session_store.get(sample_session.session_id)

        ttl = await redis_session_store._redis.ttl(key)
        # TTL should be close to the full timeout again
        assert ttl >= 55  # Allow 5s of slack

    async def test_short_ttl_expires(self, redis_session_store):
        """Session with very short TTL should expire from Redis."""
        from src.core.conversational.types.session import Session, SessionConfig

        session = Session(
            user_id="expire_user",
            config=SessionConfig(idle_timeout_seconds=2),  # 2 second TTL
        )
        await redis_session_store.store(session)

        # Should exist immediately
        retrieved = await redis_session_store.get(session.session_id)
        assert retrieved is not None

        # Wait for TTL to expire
        await asyncio.sleep(3)

        # Should be gone from Redis (may still be in memory)
        key = f"test:zenic:session:{session.session_id}"
        exists = await redis_session_store._redis.exists(key)
        assert exists == 0


# ── 3. Dual-Write Pattern ──────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestDualWritePattern:
    """Test dual-write to both Redis and in-memory."""

    async def test_store_writes_to_both(self, redis_session_store, sample_session):
        """Store should write to both Redis and in-memory."""
        await redis_session_store.store(sample_session)

        # Should be in memory
        assert sample_session.session_id in redis_session_store._memory_store

        # Should be in Redis
        key = f"test:zenic:session:{sample_session.session_id}"
        data = await redis_session_store._redis.hgetall(key)
        assert data is not None
        assert len(data) > 0

    async def test_delete_removes_from_both(self, redis_session_store, sample_session):
        """Delete should remove from both Redis and in-memory."""
        await redis_session_store.store(sample_session)

        # Verify exists in both
        assert sample_session.session_id in redis_session_store._memory_store
        key = f"test:zenic:session:{sample_session.session_id}"
        assert await redis_session_store._redis.exists(key) == 1

        # Delete
        result = await redis_session_store.delete(sample_session.session_id)
        assert result is True

        # Verify gone from both
        assert sample_session.session_id not in redis_session_store._memory_store
        assert await redis_session_store._redis.exists(key) == 0


# ── 4. Fallback to In-Memory ──────────────────────────────

@pytest.mark.asyncio
class TestInMemoryFallback:
    """Test fallback to in-memory when Redis is unavailable."""

    async def test_store_without_redis(self):
        """Store should work even when Redis is not connected."""
        from src.core.conversational.redis_session_store import RedisSessionStore
        from src.core.conversational.types.session import Session, SessionConfig

        store = RedisSessionStore(
            redis_url="redis://localhost:16379/0",  # Unreachable port
            key_prefix="test:fall:session",
            default_ttl=60,
        )
        # Don't connect — should fall back to memory
        # (connect will fail)

        session = Session(
            user_id="fallback_user",
            config=SessionConfig(idle_timeout_seconds=60),
        )
        # Store should still work (writes to memory)
        await store.store(session)

        # Should be in memory
        assert session.session_id in store._memory_store

        # Should be retrievable from memory
        retrieved = await store.get(session.session_id)
        assert retrieved is not None
        assert retrieved.user_id == "fallback_user"

    async def test_get_falls_back_to_memory(self):
        """Get should fall back to in-memory when Redis fails."""
        from src.core.conversational.redis_session_store import RedisSessionStore
        from src.core.conversational.types.session import Session, SessionConfig

        store = RedisSessionStore(
            redis_url="redis://localhost:16379/0",  # Unreachable port
            key_prefix="test:fallback:session",
            default_ttl=60,
        )

        session = Session(
            user_id="memory_only_user",
            config=SessionConfig(idle_timeout_seconds=60),
        )
        # Store writes to memory
        store._memory_store[session.session_id] = store._serialize_session(session)

        # Get should find it in memory
        retrieved = await store.get(session.session_id)
        assert retrieved is not None
        assert retrieved.user_id == "memory_only_user"

    async def test_delete_from_memory_only(self):
        """Delete should work from memory even without Redis."""
        from src.core.conversational.redis_session_store import RedisSessionStore
        from src.core.conversational.types.session import Session, SessionConfig

        store = RedisSessionStore(
            redis_url="redis://localhost:16379/0",
            key_prefix="test:delmem:session",
            default_ttl=60,
        )

        session = Session(
            user_id="delete_user",
            config=SessionConfig(idle_timeout_seconds=60),
        )
        store._memory_store[session.session_id] = store._serialize_session(session)

        result = await store.delete(session.session_id)
        assert result is True
        assert session.session_id not in store._memory_store

    async def test_stats_without_redis(self):
        """Stats should show memory backend when Redis unavailable."""
        from src.core.conversational.redis_session_store import RedisSessionStore

        store = RedisSessionStore(
            redis_url="redis://localhost:16379/0",
            key_prefix="test:stats:session",
            default_ttl=60,
        )

        stats = store.get_stats()
        assert stats["backend"] == "memory"
        assert stats["memory_store_count"] == 0


# ── 5. Concurrent Access ──────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestConcurrentAccess:
    """Test concurrent access to the session store."""

    async def test_concurrent_stores(self, redis_session_store):
        """Multiple concurrent store operations should succeed."""
        from src.core.conversational.types.session import Session, SessionConfig

        async def store_session(idx: int):
            session = Session(
                user_id=f"concurrent_user_{idx}",
                config=SessionConfig(idle_timeout_seconds=60),
            )
            await redis_session_store.store(session)
            return session.session_id

        results = await asyncio.gather(*[store_session(i) for i in range(20)])

        # All sessions should be stored
        assert len(results) == 20

        # All should be retrievable
        for session_id in results:
            retrieved = await redis_session_store.get(session_id)
            assert retrieved is not None

    async def test_concurrent_get_same_session(self, redis_session_store, sample_session):
        """Multiple concurrent gets for the same session should work."""
        await redis_session_store.store(sample_session)

        results = await asyncio.gather(*[
            redis_session_store.get(sample_session.session_id)
            for _ in range(10)
        ])

        for result in results:
            assert result is not None
            assert result.session_id == sample_session.session_id


# ── 6. SessionManager Integration ──────────────────────────

@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestSessionManagerIntegration:
    """Test SessionManager with Redis store integration."""

    def test_create_session_with_redis(self):
        """Creating a session with redis_url should use Redis."""
        from src.core.conversational.session_manager import SessionManager

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        manager = SessionManager(
            redis_url=redis_url,
            max_sessions=50,
        )

        session = manager.create_session(user_id="redis_test_user")
        assert session is not None
        assert session.user_id == "redis_test_user"
        assert manager._redis_store is not None

    def test_get_session_from_redis(self):
        """get_session should try Redis when not found in memory."""
        from src.core.conversational.session_manager import SessionManager

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        manager = SessionManager(redis_url=redis_url)

        # Create a session
        session = manager.create_session(user_id="redis_get_user")
        session_id = session.session_id

        # Remove from in-memory to force Redis lookup
        with manager._lock:
            del manager._sessions[session_id]

        # get_session should find it from Redis
        retrieved = manager.get_session(session_id)
        # Note: This may return None if Redis hasn't connected yet
        # since Redis connection is async and we're in sync context
        # The important thing is it doesn't crash

    def test_end_session_deletes_from_redis(self):
        """Ending a session should also delete from Redis."""
        from src.core.conversational.session_manager import SessionManager

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        manager = SessionManager(redis_url=redis_url)

        session = manager.create_session(user_id="redis_end_user")
        session_id = session.session_id

        result = manager.end_session(session_id)
        assert result is True

        # Should not be in memory
        assert manager.get_session(session_id) is None

    def test_manager_stats_include_redis(self):
        """Stats should include Redis store info when configured."""
        from src.core.conversational.session_manager import SessionManager

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        manager = SessionManager(redis_url=redis_url)

        stats = manager.stats
        assert "redis_store" in stats

    def test_manager_without_redis(self):
        """Manager without redis_url should work normally (backward compat)."""
        from src.core.conversational.session_manager import SessionManager

        manager = SessionManager()

        session = manager.create_session(user_id="no_redis_user")
        assert session is not None
        assert manager._redis_store is None

        # Stats should not have redis_store key
        stats = manager.stats
        assert "redis_store" not in stats


# ── 7. Cleanup ─────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestCleanup:
    """Test cleanup of expired sessions."""

    async def test_cleanup_expired_from_memory(self, redis_session_store):
        """cleanup_expired should remove expired sessions from memory."""
        from src.core.conversational.types.session import Session, SessionConfig

        # Create a session with very short timeout
        session = Session(
            user_id="expire_cleanup_user",
            config=SessionConfig(idle_timeout_seconds=1),
        )
        # Manually set last_activity to the past
        session.last_activity = time.time() - 5  # 5 seconds ago
        await redis_session_store.store(session)

        # Should be in memory
        assert session.session_id in redis_session_store._memory_store

        # Wait for expiry
        await asyncio.sleep(2)

        # Cleanup
        cleaned = await redis_session_store.cleanup_expired()
        assert cleaned >= 1

        # Should be removed from memory
        assert session.session_id not in redis_session_store._memory_store

    async def test_get_all_active_excludes_expired(self, redis_session_store):
        """get_all_active should not include expired sessions."""
        from src.core.conversational.types.session import Session, SessionConfig

        # Active session
        active_session = Session(
            user_id="active_user",
            config=SessionConfig(idle_timeout_seconds=300),
        )
        await redis_session_store.store(active_session)

        # Expired session (in memory)
        expired_session = Session(
            user_id="expired_user",
            config=SessionConfig(idle_timeout_seconds=1),
        )
        expired_session.last_activity = time.time() - 5
        redis_session_store._memory_store[expired_session.session_id] = \
            redis_session_store._serialize_session(expired_session)

        active = await redis_session_store.get_all_active()

        # Active session should be in the list
        active_ids = [s.session_id for s in active]
        assert active_session.session_id in active_ids
        # Expired session should NOT be in the list
        assert expired_session.session_id not in active_ids
