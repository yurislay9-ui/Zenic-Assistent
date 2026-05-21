"""
Redis-backed Circuit Breaker — Shared state across Python & TypeScript.

Phase 3.2: Reads/writes the same Redis keys as the TypeScript
UnifiedCircuitBreaker so that if Python opens a circuit for "memory" agent,
the gateway immediately knows, and vice versa.

State Machine (same as AgentCircuitBreaker + TypeScript UnifiedCircuitBreaker):
    CLOSED → OPEN:       failure_threshold consecutive failures
    OPEN → HALF_OPEN:    recovery_timeout_ms elapsed since last failure
    HALF_OPEN → CLOSED:  success_threshold consecutive successes
    HALF_OPEN → OPEN:    Any failure in half-open

Redis key format: zenic:cb:{name} (HASH)
    Fields: state, failureCount, successCount, lastFailureAt, lastSuccessAt, config

If Redis is unavailable, falls back to in-memory AgentCircuitBreaker.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from .circuit_breaker import AgentCircuitBreaker, CircuitBreakerManager, CircuitState

__all__ = [
    "RedisCircuitBreakerManager",
    "RedisCircuitBreakerConfig",
]


# ── Config ──────────────────────────────────────────────────


class RedisCircuitBreakerConfig:
    """Configuration for Redis-backed circuit breaker."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "zenic:cb",
        key_ttl_ms: int = 3_600_000,  # 1 hour
        fallback_cooldown_ms: int = 30_000,
    ) -> None:
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.key_ttl_ms = key_ttl_ms
        self.fallback_cooldown_ms = fallback_cooldown_ms


# ── Lua Scripts ─────────────────────────────────────────────

# These mirror the TypeScript Lua scripts exactly for consistency.

RECORD_FAILURE_SCRIPT = """
local key = KEYS[1]
local failureThreshold = tonumber(ARGV[1])
local recoveryTimeoutMs = tonumber(ARGV[2])
local successThreshold = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local ttlMs = tonumber(ARGV[5])

local data = redis.call('HMGET', key, 'state', 'failureCount', 'successCount')
local state = data[1]
local failureCount = tonumber(data[2]) or 0
local successCount = tonumber(data[3]) or 0

if state == false or state == nil then
  state = 'CLOSED'
end

local newState = state

if state == 'HALF_OPEN' then
  newState = 'OPEN'
  failureCount = failureCount + 1
  successCount = 0
elseif state == 'CLOSED' then
  failureCount = failureCount + 1
  if failureCount >= failureThreshold then
    newState = 'OPEN'
  end
elseif state == 'OPEN' then
  failureCount = failureCount + 1
end

redis.call('HMSET', key,
  'state', newState,
  'failureCount', failureCount,
  'successCount', successCount,
  'lastFailureAt', now,
  'config', cjson.encode({
    failureThreshold = failureThreshold,
    recoveryTimeoutMs = recoveryTimeoutMs,
    successThreshold = successThreshold
  })
)
redis.call('PEXPIRE', key, ttlMs)

return { newState, failureCount, successCount }
"""

RECORD_SUCCESS_SCRIPT = """
local key = KEYS[1]
local failureThreshold = tonumber(ARGV[1])
local recoveryTimeoutMs = tonumber(ARGV[2])
local successThreshold = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local ttlMs = tonumber(ARGV[5])

local data = redis.call('HMGET', key, 'state', 'failureCount', 'successCount')
local state = data[1]
local failureCount = tonumber(data[2]) or 0
local successCount = tonumber(data[3]) or 0

if state == false or state == nil then
  state = 'CLOSED'
end

local newState = state

if state == 'HALF_OPEN' then
  successCount = successCount + 1
  if successCount >= successThreshold then
    newState = 'CLOSED'
    failureCount = 0
    successCount = 0
  end
elseif state == 'CLOSED' then
  failureCount = 0
  successCount = 0
end

redis.call('HMSET', key,
  'state', newState,
  'failureCount', failureCount,
  'successCount', successCount,
  'lastSuccessAt', now,
  'config', cjson.encode({
    failureThreshold = failureThreshold,
    recoveryTimeoutMs = recoveryTimeoutMs,
    successThreshold = successThreshold
  })
)
redis.call('PEXPIRE', key, ttlMs)

return { newState, failureCount, successCount }
"""

CHECK_SCRIPT = """
local key = KEYS[1]
local failureThreshold = tonumber(ARGV[1])
local recoveryTimeoutMs = tonumber(ARGV[2])
local successThreshold = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local ttlMs = tonumber(ARGV[5])

local data = redis.call('HMGET', key, 'state', 'lastFailureAt')
local state = data[1]
local lastFailureAt = tonumber(data[2]) or 0

if state == false or state == nil then
  return { 1, 'CLOSED', 0 }
end

if state == 'CLOSED' then
  return { 1, 'CLOSED', 0 }
end

if state == 'HALF_OPEN' then
  return { 1, 'HALF_OPEN', 0 }
end

-- state == 'OPEN'
if lastFailureAt > 0 and (now - lastFailureAt) >= recoveryTimeoutMs then
  redis.call('HMSET', key, 'state', 'HALF_OPEN', 'successCount', 0)
  redis.call('PEXPIRE', key, ttlMs)
  return { 1, 'HALF_OPEN', 0 }
end

local retryAfterMs = 0
if lastFailureAt > 0 then
  retryAfterMs = math.max(0, recoveryTimeoutMs - (now - lastFailureAt))
end

return { 0, 'OPEN', retryAfterMs }
"""


# ── Redis Circuit Breaker Manager ───────────────────────────


class RedisCircuitBreakerManager(CircuitBreakerManager):
    """
    Manages per-agent circuit breaker instances with Redis-backed shared state.

    Reads/writes the same Redis keys as the TypeScript UnifiedCircuitBreaker:
        zenic:cb:{agent_name}

    Falls back to in-memory AgentCircuitBreaker when Redis is unavailable.
    All methods are async (using redis[hiredis]).
    """

    # Default circuit breaker config values
    DEFAULT_CB_CONFIG = {
        "failure_threshold": 5,
        "recovery_timeout": 30.0,  # seconds (stored as ms in Redis)
        "success_threshold": 2,
    }

    def __init__(
        self,
        redis_config: Optional[RedisCircuitBreakerConfig] = None,
    ) -> None:
        super().__init__()
        self._redis_config = redis_config or RedisCircuitBreakerConfig()
        self._redis: Any = None
        self._redis_available = False
        self._fallback_active = False
        self._fallback_count = 0
        self._fallback_last_error: Optional[str] = None
        self._fallback_since: float = 0.0
        self._initialized = False

    # ── Lifecycle ───────────────────────────────────────────────

    async def connect(self) -> None:
        """Initialize the async Redis connection."""
        if self._initialized:
            return

        try:
            from redis.asyncio import Redis as AsyncRedis

            self._redis = AsyncRedis.from_url(
                self._redis_config.redis_url,
                decode_responses=True,
            )
            # Test connection
            await self._redis.ping()
            self._redis_available = True
            self._initialized = True
        except Exception as e:
            self._handle_redis_error(e)
            self._initialized = True  # Operate in fallback

    async def disconnect(self) -> None:
        """Gracefully close the Redis connection."""
        if self._redis:
            self._redis_available = False
            try:
                await self._redis.close()
            except Exception:
                pass
            self._redis = None

    def is_redis_ready(self) -> bool:
        """Check if Redis is currently available."""
        return self._redis_available and self._redis is not None

    # ── Core Operations ────────────────────────────────────────

    async def can_call(self, agent_name: str) -> bool:
        """
        Check if agent is allowed to make a call.
        Transitions OPEN → HALF_OPEN if recovery timeout has elapsed.
        """
        if not self.is_redis_ready():
            return super().can_call(agent_name)

        try:
            config = self._get_effective_config(agent_name)
            redis_key = f"{self._redis_config.key_prefix}:{agent_name}"
            now = int(time.time() * 1000)

            result = await self._redis.eval(
                CHECK_SCRIPT,
                1,
                redis_key,
                str(config["failure_threshold"]),
                str(int(config["recovery_timeout"] * 1000)),
                str(config["success_threshold"]),
                str(now),
                str(self._redis_config.key_ttl_ms),
            )

            allowed = result[0] == 1
            # If transitioning to HALF_OPEN via Redis, update local breaker too
            if allowed and result[1] == "HALF_OPEN":
                local_breaker = self.get_breaker(agent_name)
                if local_breaker._state == CircuitState.OPEN:
                    local_breaker._transition_to(CircuitState.HALF_OPEN)

            return allowed
        except Exception as e:
            self._handle_redis_error(e)
            return super().can_call(agent_name)

    async def record_success(self, agent_name: str) -> None:
        """Record a successful call. May transition HALF_OPEN → CLOSED."""
        # Always update local breaker
        super().record_success(agent_name)

        if not self.is_redis_ready():
            return

        try:
            config = self._get_effective_config(agent_name)
            redis_key = f"{self._redis_config.key_prefix}:{agent_name}"
            now = int(time.time() * 1000)

            result = await self._redis.eval(
                RECORD_SUCCESS_SCRIPT,
                1,
                redis_key,
                str(config["failure_threshold"]),
                str(int(config["recovery_timeout"] * 1000)),
                str(config["success_threshold"]),
                str(now),
                str(self._redis_config.key_ttl_ms),
            )

            # Sync local state with Redis result
            new_state = result[0]
            if new_state == "CLOSED":
                local_breaker = self.get_breaker(agent_name)
                if local_breaker._state != CircuitState.CLOSED:
                    local_breaker._transition_to(CircuitState.CLOSED)
        except Exception as e:
            self._handle_redis_error(e)

    async def record_failure(self, agent_name: str) -> None:
        """Record a failed call. May transition CLOSED → OPEN or HALF_OPEN → OPEN."""
        # Always update local breaker
        super().record_failure(agent_name)

        if not self.is_redis_ready():
            return

        try:
            config = self._get_effective_config(agent_name)
            redis_key = f"{self._redis_config.key_prefix}:{agent_name}"
            now = int(time.time() * 1000)

            result = await self._redis.eval(
                RECORD_FAILURE_SCRIPT,
                1,
                redis_key,
                str(config["failure_threshold"]),
                str(int(config["recovery_timeout"] * 1000)),
                str(config["success_threshold"]),
                str(now),
                str(self._redis_config.key_ttl_ms),
            )

            # Sync local state with Redis result
            new_state = result[0]
            if new_state == "OPEN":
                local_breaker = self.get_breaker(agent_name)
                if local_breaker._state != CircuitState.OPEN:
                    local_breaker._transition_to(CircuitState.OPEN)
        except Exception as e:
            self._handle_redis_error(e)

    async def reset(self, agent_name: str) -> None:
        """Force circuit to CLOSED state in both Redis and local."""
        super().reset(agent_name)

        if not self.is_redis_ready():
            return

        try:
            redis_key = f"{self._redis_config.key_prefix}:{agent_name}"
            await self._redis.delete(redis_key)
        except Exception as e:
            self._handle_redis_error(e)

    async def all_stats(self) -> Dict[str, Dict]:
        """
        Get stats for all known circuits.
        Merges local in-memory stats with Redis data.
        """
        # Start with local stats
        local_stats = super().all_stats()

        if not self.is_redis_ready():
            return local_stats

        try:
            # Scan Redis for all circuit keys
            pattern = f"{self._redis_config.key_prefix}:*"
            cursor = 0
            redis_keys: list = []

            while True:
                cursor, keys = await self._redis.scan(
                    cursor=cursor, match=pattern, count=100
                )
                redis_keys.extend(keys)
                if cursor == 0:
                    break

            # Get Redis data for each key
            for key in redis_keys:
                name = key[len(self._redis_config.key_prefix) + 1 :]
                data = await self._redis.hgetall(key)

                if data and "state" in data:
                    config = self._get_effective_config(name)
                    if "config" in data:
                        try:
                            parsed_config = json.loads(data["config"])
                            config = {
                                "failure_threshold": parsed_config.get(
                                    "failureThreshold", config["failure_threshold"]
                                ),
                                "recovery_timeout": parsed_config.get(
                                    "recoveryTimeoutMs", config["recovery_timeout"] * 1000
                                )
                                / 1000,
                                "success_threshold": parsed_config.get(
                                    "successThreshold", config["success_threshold"]
                                ),
                            }
                        except (json.JSONDecodeError, KeyError):
                            pass

                    redis_stats = {
                        "name": name,
                        "state": data["state"],
                        "failure_count": int(data.get("failureCount", 0)),
                        "success_count": int(data.get("successCount", 0)),
                        "last_failure_at": int(data.get("lastFailureAt", 0)),
                        "last_success_at": int(data.get("lastSuccessAt", 0)),
                        "config": config,
                        "source": "redis",
                    }
                    local_stats[name] = redis_stats

            # Mark local-only stats
            for name in local_stats:
                if "source" not in local_stats[name]:
                    local_stats[name]["source"] = "memory"

            return local_stats
        except Exception as e:
            self._handle_redis_error(e)
            return local_stats

    async def get_stats(self, agent_name: str) -> Optional[Dict]:
        """
        Get stats for a specific circuit from Redis.
        Falls back to local stats if Redis is unavailable.
        """
        if not self.is_redis_ready():
            local = super().all_stats()
            return local.get(agent_name)

        try:
            redis_key = f"{self._redis_config.key_prefix}:{agent_name}"
            data = await self._redis.hgetall(redis_key)

            if not data or "state" not in data:
                # Fall back to local
                local = super().all_stats()
                return local.get(agent_name)

            config = self._get_effective_config(agent_name)
            if "config" in data:
                try:
                    parsed_config = json.loads(data["config"])
                    config = {
                        "failure_threshold": parsed_config.get(
                            "failureThreshold", config["failure_threshold"]
                        ),
                        "recovery_timeout": parsed_config.get(
                            "recoveryTimeoutMs", config["recovery_timeout"] * 1000
                        )
                        / 1000,
                        "success_threshold": parsed_config.get(
                            "successThreshold", config["success_threshold"]
                        ),
                    }
                except (json.JSONDecodeError, KeyError):
                    pass

            return {
                "name": agent_name,
                "state": data["state"],
                "failure_count": int(data.get("failureCount", 0)),
                "success_count": int(data.get("successCount", 0)),
                "last_failure_at": int(data.get("lastFailureAt", 0)),
                "last_success_at": int(data.get("lastSuccessAt", 0)),
                "config": config,
                "source": "redis",
            }
        except Exception as e:
            self._handle_redis_error(e)
            local = super().all_stats()
            return local.get(agent_name)

    # ── Fallback State ─────────────────────────────────────────

    def get_fallback_state(self) -> Dict[str, Any]:
        """Get current fallback state for monitoring."""
        return {
            "active": self._fallback_active,
            "since": self._fallback_since,
            "fallback_count": self._fallback_count,
            "last_error": self._fallback_last_error,
        }

    # ── Internal Helpers ───────────────────────────────────────

    def _get_effective_config(self, agent_name: str) -> Dict[str, Any]:
        """Get the effective config for an agent, applying group defaults."""
        group = self._classify_agent(agent_name)
        group_config = self.DEFAULT_CONFIGS.get(
            group, {"failure_threshold": 3, "recovery_timeout": 60.0}
        )
        return {
            "failure_threshold": group_config.get("failure_threshold", 3),
            "recovery_timeout": group_config.get("recovery_timeout", 60.0),
            "success_threshold": group_config.get("success_threshold", 2),
        }

    def _handle_redis_error(self, err: Exception) -> None:
        """Handle Redis errors by activating fallback mode."""
        message = str(err)
        if not self._fallback_active:
            self._fallback_active = True
            self._fallback_since = time.monotonic()
            self._fallback_count += 1
        self._fallback_last_error = message
        self._redis_available = False
