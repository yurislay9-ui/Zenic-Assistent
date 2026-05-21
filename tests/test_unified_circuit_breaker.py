"""
ZENIC-AGENTS — Unified Circuit Breaker Test Suite (Phase 3.2: Resilience)

Tests for the RedisCircuitBreakerManager that shares circuit breaker state
between Python and TypeScript via Redis.

Test coverage:
1. State transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
2. Redis key format verification (zenic:cb:{name})
3. Fallback to in-memory when Redis unavailable
4. Concurrent access safety
5. Stats collection
6. Cross-language state sharing (Python reads what TS writes)

All Redis-dependent tests are automatically skipped if Redis is not available.
Run with:  pytest tests/test_unified_circuit_breaker.py -v
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


# Skip all Redis tests if Redis is not reachable
redis_not_available = not _redis_available()
SKIP_REASON = (
    "Redis is not available. "
    "Start it with: docker compose up -d redis"
)


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def redis_url() -> str:
    """Return the Redis URL for testing."""
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@pytest_asyncio.fixture(scope="module")
async def redis_async_client(redis_url: str):
    """Create an async Redis client for the test module."""
    if redis_not_available:
        pytest.skip(SKIP_REASON)

    try:
        from redis.asyncio import Redis as AsyncRedis
    except ImportError:
        pytest.skip("redis.asyncio not available — install redis[hiredis]")

    client = AsyncRedis.from_url(redis_url, decode_responses=True)
    yield client
    # Cleanup test keys
    try:
        async for key in client.scan_iter("zenic:cb:test*"):
            await client.delete(key)
    except Exception:
        pass
    await client.close()


@pytest_asyncio.fixture
async def cb_manager(redis_url: str):
    """Create a fresh RedisCircuitBreakerManager for each test."""
    from src.core.agents.resilience.redis_circuit_breaker import (
        RedisCircuitBreakerConfig,
        RedisCircuitBreakerManager,
    )

    config = RedisCircuitBreakerConfig(
        redis_url=redis_url,
        key_prefix="zenic:cb:test",
        key_ttl_ms=60000,  # 1 minute TTL for tests
    )
    manager = RedisCircuitBreakerManager(redis_config=config)
    await manager.connect()
    yield manager
    # Cleanup
    try:
        await manager.disconnect()
    except Exception:
        pass


# ── 1. State Transitions ────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestStateTransitions:
    """Test circuit breaker state machine: CLOSED → OPEN → HALF_OPEN → CLOSED."""

    async def test_initial_state_is_closed(self, cb_manager):
        """New circuit should start in CLOSED state."""
        assert await cb_manager.can_call("test_agent_initial") is True

    async def test_closed_to_open_transition(self, cb_manager):
        """Circuit should transition from CLOSED to OPEN after failure_threshold failures."""
        agent = "test_agent_closed_open"
        # Default memory group has failure_threshold=5
        config = cb_manager._get_effective_config(agent)
        threshold = config["failure_threshold"]

        # Record failures up to threshold
        for _ in range(threshold):
            await cb_manager.record_failure(agent)

        # Circuit should now be OPEN — calls are blocked
        assert await cb_manager.can_call(agent) is False

    async def test_open_to_half_open_after_recovery_timeout(self, cb_manager, redis_async_client):
        """Circuit should transition from OPEN to HALF_OPEN after recovery timeout."""
        agent = "test_agent_open_halfopen"
        config = cb_manager._get_effective_config(agent)

        # Open the circuit
        for _ in range(config["failure_threshold"]):
            await cb_manager.record_failure(agent)

        # Should be OPEN
        assert await cb_manager.can_call(agent) is False

        # Simulate recovery timeout by modifying lastFailureAt in Redis
        redis_key = f"zenic:cb:test:{agent}"
        recovery_ms = int(config["recovery_timeout"] * 1000)
        old_time = int(time.time() * 1000) - recovery_ms - 1000  # 1s past timeout
        await redis_async_client.hset(redis_key, "lastFailureAt", str(old_time))

        # Should now transition to HALF_OPEN — call is allowed
        assert await cb_manager.can_call(agent) is True

    async def test_half_open_to_closed_on_success_threshold(self, cb_manager, redis_async_client):
        """Circuit should transition from HALF_OPEN to CLOSED after success_threshold successes."""
        agent = "test_agent_halfopen_closed"
        config = cb_manager._get_effective_config(agent)

        # Open the circuit
        for _ in range(config["failure_threshold"]):
            await cb_manager.record_failure(agent)

        # Force to HALF_OPEN by setting lastFailureAt to past
        redis_key = f"zenic:cb:test:{agent}"
        recovery_ms = int(config["recovery_timeout"] * 1000)
        old_time = int(time.time() * 1000) - recovery_ms - 1000
        await redis_async_client.hset(redis_key, "lastFailureAt", str(old_time))

        # Now in HALF_OPEN
        assert await cb_manager.can_call(agent) is True

        # Record enough successes to close
        for _ in range(config["success_threshold"]):
            await cb_manager.record_success(agent)

        # Should be CLOSED now
        stats = await cb_manager.get_stats(agent)
        assert stats is not None
        assert stats["state"] == "CLOSED"

    async def test_half_open_to_open_on_failure(self, cb_manager, redis_async_client):
        """Any failure in HALF_OPEN should transition back to OPEN."""
        agent = "test_agent_halfopen_open"
        config = cb_manager._get_effective_config(agent)

        # Open the circuit
        for _ in range(config["failure_threshold"]):
            await cb_manager.record_failure(agent)

        # Force to HALF_OPEN
        redis_key = f"zenic:cb:test:{agent}"
        recovery_ms = int(config["recovery_timeout"] * 1000)
        old_time = int(time.time() * 1000) - recovery_ms - 1000
        await redis_async_client.hset(redis_key, "lastFailureAt", str(old_time))

        # Confirm in HALF_OPEN
        assert await cb_manager.can_call(agent) is True

        # Record a single failure — should go back to OPEN
        await cb_manager.record_failure(agent)

        # Should be OPEN again
        stats = await cb_manager.get_stats(agent)
        assert stats is not None
        assert stats["state"] == "OPEN"


# ── 2. Redis Key Format Verification ───────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestRedisKeyFormat:
    """Verify that Redis keys follow the zenic:cb:{name} format."""

    async def test_key_format_in_redis(self, cb_manager, redis_async_client):
        """Recorded failures should create keys in zenic:cb:{name} format."""
        agent = "test_key_format_agent"
        await cb_manager.record_failure(agent)

        # Check the key exists in Redis
        redis_key = f"zenic:cb:test:{agent}"
        exists = await redis_async_client.exists(redis_key)
        assert exists == 1

    async def test_hash_fields_in_redis(self, cb_manager, redis_async_client):
        """Redis hash should contain all required fields."""
        agent = "test_hash_fields_agent"
        await cb_manager.record_failure(agent)

        redis_key = f"zenic:cb:test:{agent}"
        data = await redis_async_client.hgetall(redis_key)

        # Verify required fields exist
        assert "state" in data
        assert "failureCount" in data
        assert "successCount" in data
        assert "lastFailureAt" in data
        assert "config" in data

    async def test_config_stored_as_json(self, cb_manager, redis_async_client):
        """Config field should be stored as JSON with correct structure."""
        import json

        agent = "test_config_json_agent"
        await cb_manager.record_failure(agent)

        redis_key = f"zenic:cb:test:{agent}"
        data = await redis_async_client.hgetall(redis_key)

        config = json.loads(data["config"])
        assert "failureThreshold" in config
        assert "recoveryTimeoutMs" in config
        assert "successThreshold" in config

    async def test_ttl_set_on_redis_key(self, cb_manager, redis_async_client):
        """Redis key should have TTL set for auto-cleanup."""
        agent = "test_ttl_agent"
        await cb_manager.record_failure(agent)

        redis_key = f"zenic:cb:test:{agent}"
        ttl = await redis_async_client.pttl(redis_key)
        assert ttl > 0  # Key should have a TTL


# ── 3. Fallback to In-Memory ───────────────────────────────

@pytest.mark.asyncio
class TestFallbackToInMemory:
    """Test fallback to in-memory circuit breaker when Redis is unavailable."""

    async def test_fallback_without_redis(self):
        """Should fall back to in-memory when Redis is unavailable."""
        from src.core.agents.resilience.redis_circuit_breaker import (
            RedisCircuitBreakerConfig,
            RedisCircuitBreakerManager,
        )

        config = RedisCircuitBreakerConfig(
            redis_url="redis://localhost:16379/0",  # Unreachable port
            key_prefix="zenic:cb:test",
        )
        manager = RedisCircuitBreakerManager(redis_config=config)
        await manager.connect()

        # Should be in fallback mode
        assert manager.is_redis_ready() is False
        fallback_state = manager.get_fallback_state()
        assert fallback_state["active"] is True

        # Should still work via in-memory fallback
        assert await manager.can_call("fallback_agent") is True

        # Record failures and open circuit
        config_dict = manager._get_effective_config("fallback_agent")
        for _ in range(config_dict["failure_threshold"]):
            await manager.record_failure("fallback_agent")

        # Circuit should be open in memory
        assert await manager.can_call("fallback_agent") is False

        await manager.disconnect()

    async def test_fallback_stats_available(self):
        """Stats should still be available in fallback mode."""
        from src.core.agents.resilience.redis_circuit_breaker import (
            RedisCircuitBreakerConfig,
            RedisCircuitBreakerManager,
        )

        config = RedisCircuitBreakerConfig(
            redis_url="redis://localhost:16379/0",
            key_prefix="zenic:cb:test",
        )
        manager = RedisCircuitBreakerManager(redis_config=config)
        await manager.connect()

        # Record some activity
        await manager.can_call("fallback_stats_agent")
        await manager.record_failure("fallback_stats_agent")

        # Stats should work
        stats = await manager.all_stats()
        assert isinstance(stats, dict)
        assert "fallback_stats_agent" in stats

        await manager.disconnect()


# ── 4. Concurrent Access Safety ─────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestConcurrentAccess:
    """Test concurrent access safety for the circuit breaker."""

    async def test_concurrent_record_failures(self, cb_manager):
        """Multiple concurrent record_failure calls should not corrupt state."""
        agent = "test_concurrent_agent"

        async def record_fail():
            await cb_manager.record_failure(agent)

        # Fire 10 concurrent failures
        await asyncio.gather(*[record_fail() for _ in range(10)])

        # Circuit should be OPEN (failure count >= threshold)
        stats = await cb_manager.get_stats(agent)
        assert stats is not None
        assert stats["state"] == "OPEN"
        # Failure count should be exactly 10 (not more due to races)
        assert stats["failure_count"] == 10

    async def test_concurrent_mixed_operations(self, cb_manager):
        """Mixed concurrent success/failure operations should be safe."""
        agent = "test_mixed_concurrent_agent"

        async def record_success():
            await cb_manager.record_success(agent)

        async def record_failure():
            await cb_manager.record_failure(agent)

        async def check():
            return await cb_manager.can_call(agent)

        # Run mixed operations concurrently
        results = await asyncio.gather(
            record_failure(),
            record_failure(),
            record_success(),
            record_failure(),
            check(),
            record_failure(),
            record_failure(),
            check(),
        )

        # No exceptions should be raised — all operations completed
        assert all(r is None or isinstance(r, (bool,)) for r in results)


# ── 5. Stats Collection ────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestStatsCollection:
    """Test stats collection from the circuit breaker."""

    async def test_all_stats_returns_dict(self, cb_manager):
        """all_stats() should return a dictionary of circuit stats."""
        await cb_manager.record_failure("stats_test_agent")
        stats = await cb_manager.all_stats()
        assert isinstance(stats, dict)

    async def test_stats_include_required_fields(self, cb_manager):
        """Stats should include all required fields."""
        agent = "stats_fields_agent"
        await cb_manager.record_failure(agent)

        stats = await cb_manager.get_stats(agent)
        assert stats is not None
        assert "name" in stats
        assert "state" in stats
        assert "failure_count" in stats
        assert "success_count" in stats

    async def test_stats_failure_count_increments(self, cb_manager):
        """failure_count should increment with each failure."""
        agent = "stats_increment_agent"
        for i in range(3):
            await cb_manager.record_failure(agent)

        stats = await cb_manager.get_stats(agent)
        assert stats is not None
        assert stats["failure_count"] == 3

    async def test_reset_clears_circuit(self, cb_manager):
        """reset() should clear circuit state in both Redis and local."""
        agent = "stats_reset_agent"
        config = cb_manager._get_effective_config(agent)

        # Open the circuit
        for _ in range(config["failure_threshold"]):
            await cb_manager.record_failure(agent)

        # Verify it's open
        assert await cb_manager.can_call(agent) is False

        # Reset
        await cb_manager.reset(agent)

        # Should be closed again
        assert await cb_manager.can_call(agent) is True

    async def test_stats_source_indicates_redis(self, cb_manager):
        """Stats from Redis should indicate 'redis' source."""
        agent = "stats_source_agent"
        await cb_manager.record_failure(agent)

        stats = await cb_manager.get_stats(agent)
        assert stats is not None
        assert stats.get("source") == "redis"


# ── 6. Cross-Language State Sharing ────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestCrossLanguageStateSharing:
    """Test that Python can read state written by TypeScript and vice versa."""

    async def test_python_reads_ts_written_state(self, cb_manager, redis_async_client):
        """Python should read circuit state that was directly written to Redis (simulating TS write)."""
        import json

        agent = "cross_lang_agent"
        redis_key = f"zenic:cb:test:{agent}"

        # Simulate TypeScript writing state to Redis
        config = cb_manager._get_effective_config(agent)
        await redis_async_client.hset(
            redis_key,
            mapping={
                "state": "OPEN",
                "failureCount": "5",
                "successCount": "0",
                "lastFailureAt": str(int(time.time() * 1000)),
                "lastSuccessAt": "0",
                "config": json.dumps({
                    "failureThreshold": config["failure_threshold"],
                    "recoveryTimeoutMs": int(config["recovery_timeout"] * 1000),
                    "successThreshold": config["success_threshold"],
                }),
            },
        )
        await redis_async_client.pexpire(redis_key, 60000)

        # Python should see the circuit as OPEN
        result = await cb_manager.can_call(agent)
        assert result is False

    async def test_python_writes_ts_readable_state(self, cb_manager, redis_async_client):
        """Python-written state should be in a format TypeScript can read."""
        agent = "cross_lang_write_agent"
        await cb_manager.record_failure(agent)

        redis_key = f"zenic:cb:test:{agent}"
        data = await redis_async_client.hgetall(redis_key)

        # Verify the key format matches what TS expects
        assert "state" in data
        assert data["state"] in ("CLOSED", "OPEN", "HALF_OPEN")
        assert "failureCount" in data
        assert "successCount" in data
        assert "lastFailureAt" in data

        # Config should be valid JSON
        import json
        config = json.loads(data["config"])
        assert "failureThreshold" in config
        assert "recoveryTimeoutMs" in config
        assert "successThreshold" in config


# ── 7. In-Memory CircuitBreakerManager (Baseline) ──────────

class TestInMemoryBaseline:
    """Test the base CircuitBreakerManager still works (no Redis needed)."""

    def test_in_memory_can_call(self):
        """In-memory CircuitBreakerManager should allow calls."""
        from src.core.agents.resilience.circuit_breaker import CircuitBreakerManager

        manager = CircuitBreakerManager()
        assert manager.can_call("test_agent") is True

    def test_in_memory_record_failure(self):
        """In-memory manager should track failures and open circuit."""
        from src.core.agents.resilience.circuit_breaker import CircuitBreakerManager

        manager = CircuitBreakerManager()
        # Get the config for this agent
        breaker = manager.get_breaker("test_agent")
        for _ in range(breaker.failure_threshold):
            manager.record_failure("test_agent")

        assert manager.can_call("test_agent") is False

    def test_in_memory_all_stats(self):
        """In-memory manager should return stats."""
        from src.core.agents.resilience.circuit_breaker import CircuitBreakerManager

        manager = CircuitBreakerManager()
        manager.record_failure("test_stats_agent")
        stats = manager.all_stats()
        assert "test_stats_agent" in stats
        assert stats["test_stats_agent"]["failure_count"] == 1
