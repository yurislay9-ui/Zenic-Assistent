"""
ZENIC-AGENTS v16 — Redis Integration Test Suite (Phase 2: Scalability)

Integration tests for Python Redis connectivity, verifying:
1. Ping command (connectivity check)
2. Set/Get with TTL (expiry behavior)
3. Key prefix isolation (multi-tenant safety)
4. Connection error handling (unreachable host)
5. Async Redis operations (redis[hiredis] async support)

All tests are automatically skipped if Redis is not available.
Run with:  pytest tests/test_redis_integration.py -v
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

@pytest.fixture(scope="module")
def redis_url() -> str:
    """Return the Redis URL for testing."""
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture(scope="module")
def redis_client(redis_url: str):
    """Create a synchronous Redis client for the test module."""
    if redis_not_available:
        pytest.skip(SKIP_REASON)

    import redis as rd
    client = rd.from_url(redis_url, decode_responses=True)
    yield client
    # Cleanup test keys
    try:
        for key in client.keys("test:*"):
            client.delete(key)
    except Exception:
        pass
    client.close()


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
        async for key in client.scan_iter("atest:*"):
            await client.delete(key)
    except Exception:
        pass
    await client.close()


# ── 1. Ping / Connectivity ──────────────────────────────────

@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestPing:
    """Test Redis PING command and connectivity."""

    def test_ping_returns_pong(self, redis_client):
        """PING should return True (or PONG)."""
        result = redis_client.ping()
        assert result is True

    def test_ping_with_message(self, redis_client):
        """PING with a message should echo it back."""
        result = redis_client.ping("hello")
        assert result == "hello"

    def test_connection_info(self, redis_client):
        """Client should be connected and able to retrieve server info."""
        info = redis_client.info("server")
        assert "redis_version" in info
        assert info["redis_version"].startswith("7")


# ── 2. Set/Get with TTL ─────────────────────────────────────

@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestSetGetWithTTL:
    """Test SET/GET operations with TTL (expiry)."""

    def test_set_and_get(self, redis_client):
        """Basic SET and GET should work."""
        redis_client.set("test:simple", "hello")
        result = redis_client.get("test:simple")
        assert result == "hello"

    def test_set_with_ttl(self, redis_client):
        """SET with EX (expiry) should expire after TTL."""
        redis_client.set("test:ttl_key", "temporary", ex=2)
        result = redis_client.get("test:ttl_key")
        assert result == "temporary"

        # Wait for expiry
        time.sleep(2.5)
        result = redis_client.get("test:ttl_key")
        assert result is None

    def test_setex(self, redis_client):
        """SETEX should set key with expiry in one call."""
        redis_client.setex("test:setex_key", 2, "short_lived")
        ttl = redis_client.ttl("test:setex_key")
        assert ttl > 0
        assert ttl <= 2

        result = redis_client.get("test:setex_key")
        assert result == "short_lived"

    def test_ttl_on_nonexistent_key(self, redis_client):
        """TTL on a non-existent key should return -2."""
        ttl = redis_client.ttl("test:nonexistent_key_xyz")
        assert ttl == -2

    def test_ttl_on_key_without_expiry(self, redis_client):
        """TTL on a key without expiry should return -1."""
        redis_client.set("test:no_expiry", "persistent")
        ttl = redis_client.ttl("test:no_expiry")
        assert ttl == -1

    def test_persist_removes_ttl(self, redis_client):
        """PERSIST should remove TTL from a key."""
        redis_client.setex("test:persist_key", 60, "data")
        ttl_before = redis_client.ttl("test:persist_key")
        assert ttl_before > 0

        redis_client.persist("test:persist_key")
        ttl_after = redis_client.ttl("test:persist_key")
        assert ttl_after == -1

    def test_delete_key(self, redis_client):
        """DEL should remove a key."""
        redis_client.set("test:del_key", "bye")
        assert redis_client.get("test:del_key") == "bye"
        redis_client.delete("test:del_key")
        assert redis_client.get("test:del_key") is None

    def test_exists(self, redis_client):
        """EXISTS should return 1 for existing keys, 0 for missing."""
        redis_client.set("test:exists_key", "yes")
        assert redis_client.exists("test:exists_key") == 1
        assert redis_client.exists("test:no_such_key") == 0

    def test_mset_and_mget(self, redis_client):
        """MSET/MGET should handle multiple keys."""
        redis_client.mset({
            "test:multi_a": "value_a",
            "test:multi_b": "value_b",
            "test:multi_c": "value_c",
        })
        results = redis_client.mget("test:multi_a", "test:multi_b", "test:multi_c")
        assert results == ["value_a", "value_b", "value_c"]


# ── 3. Key Prefix Isolation ─────────────────────────────────

@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestKeyPrefixIsolation:
    """Test key prefix isolation for multi-tenant safety."""

    def test_different_prefixes_isolated(self, redis_client):
        """Keys with different prefixes should not interfere."""
        redis_client.set("test:tenant_a:key1", "data_a")
        redis_client.set("test:tenant_b:key1", "data_b")

        assert redis_client.get("test:tenant_a:key1") == "data_a"
        assert redis_client.get("test:tenant_b:key1") == "data_b"

        # Deleting tenant_a's key should not affect tenant_b
        redis_client.delete("test:tenant_a:key1")
        assert redis_client.get("test:tenant_a:key1") is None
        assert redis_client.get("test:tenant_b:key1") == "data_b"

    def test_scan_with_pattern(self, redis_client):
        """SCAN should filter keys by pattern (prefix-based isolation)."""
        redis_client.set("test:iso_a:item1", "v1")
        redis_client.set("test:iso_a:item2", "v2")
        redis_client.set("test:iso_b:item1", "v3")

        keys_a = list(redis_client.scan_iter("test:iso_a:*"))
        keys_b = list(redis_client.scan_iter("test:iso_b:*"))

        assert len(keys_a) >= 2
        assert len(keys_b) >= 1
        assert not any("iso_b" in k for k in keys_a)
        assert not any("iso_a" in k for k in keys_b)

    def test_prefix_deletion_does_not_affect_others(self, redis_client):
        """Deleting keys by prefix should not affect other prefixes."""
        for i in range(5):
            redis_client.set(f"test:del_a:key{i}", f"val_a_{i}")
            redis_client.set(f"test:del_b:key{i}", f"val_b_{i}")

        # Delete all keys with prefix del_a
        keys_to_delete = list(redis_client.scan_iter("test:del_a:*"))
        if keys_to_delete:
            redis_client.delete(*keys_to_delete)

        # Verify del_b keys are intact
        remaining_b = list(redis_client.scan_iter("test:del_b:*"))
        assert len(remaining_b) == 5

    def test_namespace_collision_avoided(self, redis_client):
        """Same key name under different prefixes are distinct keys."""
        redis_client.set("test:ns_x:config", "x_config")
        redis_client.set("test:ns_y:config", "y_config")

        assert redis_client.get("test:ns_x:config") == "x_config"
        assert redis_client.get("test:ns_y:config") == "y_config"


# ── 4. Connection Error Handling ─────────────────────────────

@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestConnectionErrorHandling:
    """Test error handling for connection failures."""

    def test_connection_refused(self):
        """Connecting to a non-existent Redis should raise ConnectionError."""
        import redis as rd
        client = rd.from_url(
            "redis://localhost:16379/0",  # Unlikely port
            socket_connect_timeout=2,
        )
        with pytest.raises(Exception):
            client.ping()
        client.close()

    def test_invalid_url_raises(self):
        """An invalid Redis URL should raise an error on connection."""
        import redis as rd
        client = rd.from_url("redis://nonexistent.host:6379/0", socket_connect_timeout=2)
        with pytest.raises(Exception):
            client.ping()
        client.close()

    def test_wrong_type_operation(self, redis_client):
        """Operating on a key with wrong type should raise ResponseError."""
        redis_client.set("test:string_key", "string_value")
        # Trying LIST operation on a STRING key should fail
        with pytest.raises(Exception):
            redis_client.lpush("test:string_key", "list_item")


# ── 5. Async Redis Operations ───────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestAsyncRedisOperations:
    """Test async Redis client operations (redis[hiredis])."""

    async def test_async_ping(self, redis_async_client):
        """Async PING should return True."""
        result = await redis_async_client.ping()
        assert result is True

    async def test_async_set_and_get(self, redis_async_client):
        """Async SET/GET should work."""
        await redis_async_client.set("atest:simple", "async_hello")
        result = await redis_async_client.get("atest:simple")
        assert result == "async_hello"

    async def test_async_set_with_ttl(self, redis_async_client):
        """Async SET with EX should set TTL."""
        await redis_async_client.set("atest:ttl", "temp", ex=5)
        ttl = await redis_async_client.ttl("atest:ttl")
        assert 0 < ttl <= 5

    async def test_async_delete(self, redis_async_client):
        """Async DEL should remove keys."""
        await redis_async_client.set("atest:del", "bye")
        result = await redis_async_client.get("atest:del")
        assert result == "bye"
        await redis_async_client.delete("atest:del")
        result = await redis_async_client.get("atest:del")
        assert result is None

    async def test_async_exists(self, redis_async_client):
        """Async EXISTS should check key existence."""
        await redis_async_client.set("atest:exists", "yes")
        exists = await redis_async_client.exists("atest:exists")
        assert exists == 1
        exists_missing = await redis_async_client.exists("atest:no_such_key")
        assert exists_missing == 0

    async def test_async_prefix_isolation(self, redis_async_client):
        """Async operations should respect key prefix isolation."""
        await redis_async_client.set("atest:pa:key1", "value_a")
        await redis_async_client.set("atest:pb:key1", "value_b")

        val_a = await redis_async_client.get("atest:pa:key1")
        val_b = await redis_async_client.get("atest:pb:key1")
        assert val_a == "value_a"
        assert val_b == "value_b"

        await redis_async_client.delete("atest:pa:key1")
        val_a_after = await redis_async_client.get("atest:pa:key1")
        val_b_after = await redis_async_client.get("atest:pb:key1")
        assert val_a_after is None
        assert val_b_after == "value_b"

    async def test_async_concurrent_operations(self, redis_async_client):
        """Multiple concurrent async operations should succeed."""
        async def set_and_get(idx: int):
            key = f"atest:concurrent:{idx}"
            await redis_async_client.set(key, f"val_{idx}")
            val = await redis_async_client.get(key)
            return val

        results = await asyncio.gather(*[set_and_get(i) for i in range(20)])
        for idx, val in enumerate(results):
            assert val == f"val_{idx}"

    async def test_async_connection_error(self):
        """Async connection to non-existent Redis should raise error."""
        try:
            from redis.asyncio import Redis as AsyncRedis
        except ImportError:
            pytest.skip("redis.asyncio not available")

        client = AsyncRedis.from_url(
            "redis://localhost:16379/0",
            socket_connect_timeout=2,
        )
        with pytest.raises(Exception):
            await client.ping()
        await client.close()


# ── 6. Redis Data Type Operations ───────────────────────────

@pytest.mark.skipif(redis_not_available, reason=SKIP_REASON)
class TestRedisDataTypes:
    """Test various Redis data types for caching use cases."""

    def test_hash_operations(self, redis_client):
        """HSET/HGET should work for hash data (useful for tenant config)."""
        redis_client.hset("test:tenant:config", mapping={
            "plan": "pro",
            "rate_limit": "1000",
            "active": "true",
        })
        plan = redis_client.hget("test:tenant:config", "plan")
        assert plan == "pro"

        all_fields = redis_client.hgetall("test:tenant:config")
        assert all_fields["plan"] == "pro"
        assert all_fields["rate_limit"] == "1000"

    def test_set_operations(self, redis_client):
        """SADD/SMEMBERS should work for set data (useful for revocation lists)."""
        redis_client.sadd("test:revoked_tokens", "token_a", "token_b", "token_c")
        members = redis_client.smembers("test:revoked_tokens")
        assert "token_a" in members
        assert len(members) == 3

        redis_client.srem("test:revoked_tokens", "token_a")
        assert redis_client.sismember("test:revoked_tokens", "token_a") is False

    def test_incr_decr(self, redis_client):
        """INCR/DECR should work for counters (useful for rate limiting)."""
        redis_client.set("test:counter", "0")
        redis_client.incr("test:counter")
        redis_client.incr("test:counter")
        redis_client.incr("test:counter", 5)
        assert int(redis_client.get("test:counter")) == 7

        redis_client.decr("test:counter", 3)
        assert int(redis_client.get("test:counter")) == 4
