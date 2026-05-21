/**
 * Unified Circuit Breaker — Redis-backed shared state across TypeScript & Python
 *
 * Phase 3.2: Coordinates circuit breaker state between the TypeScript gateway
 * and Python backend via Redis. If Python opens a circuit for "memory" agent,
 * the gateway immediately knows and vice versa.
 *
 * State Machine (same as Python AgentCircuitBreaker):
 *   CLOSED → OPEN:       failureThreshold consecutive failures
 *   OPEN → HALF_OPEN:    recoveryTimeoutMs elapsed since last failure
 *   HALF_OPEN → CLOSED:  successThreshold consecutive successes
 *   HALF_OPEN → OPEN:    Any failure in half-open
 *
 * Redis key format: zenic:cb:{name} (HASH)
 *   Fields: state, failureCount, successCount, lastFailureAt, lastSuccessAt, config
 *
 * If Redis is unavailable, falls back to local in-memory circuit breaker
 * (same behaviour as the original CircuitBreaker in resource-governor.ts).
 */

import Redis from "ioredis";

// ===== TYPES =====

export type CircuitState = "CLOSED" | "OPEN" | "HALF_OPEN";

export interface CircuitBreakerConfig {
  /** Failures before opening the circuit (default: 5) */
  failureThreshold: number;
  /** Ms before an OPEN circuit transitions to HALF_OPEN (default: 30000) */
  recoveryTimeoutMs: number;
  /** Consecutive successes in HALF_OPEN to close the circuit (default: 2) */
  successThreshold: number;
}

export interface CircuitBreakerStats {
  name: string;
  state: CircuitState;
  failureCount: number;
  successCount: number;
  lastFailureAt: number;
  lastSuccessAt: number;
  config: CircuitBreakerConfig;
}

export interface CircuitCheckResult {
  allowed: boolean;
  state: CircuitState;
  retryAfterMs: number;
}

export const DEFAULT_CB_CONFIG: CircuitBreakerConfig = {
  failureThreshold: 5,
  recoveryTimeoutMs: 30000,
  successThreshold: 2,
};

// ===== LUA SCRIPTS =====

/**
 * RECORD_FAILURE Lua Script
 *
 * Atomically increments the failure count and transitions state:
 *   CLOSED → OPEN      if failureCount >= failureThreshold
 *   HALF_OPEN → OPEN   on any failure (reset successCount)
 *
 * KEYS[1] = zenic:cb:{name}
 * ARGV[1] = failureThreshold
 * ARGV[2] = recoveryTimeoutMs
 * ARGV[3] = successThreshold
 * ARGV[4] = current timestamp (ms)
 * ARGV[5] = TTL for the key (ms)
 *
 * Returns: { newState, failureCount, successCount }
 */
const RECORD_FAILURE_SCRIPT = `
local key = KEYS[1]
local failureThreshold = tonumber(ARGV[1])
local recoveryTimeoutMs = tonumber(ARGV[2])
local successThreshold = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local ttlMs = tonumber(ARGV[5])

-- Read current state
local data = redis.call('HMGET', key, 'state', 'failureCount', 'successCount')
local state = data[1]
local failureCount = tonumber(data[2]) or 0
local successCount = tonumber(data[3]) or 0

-- If no state yet, default to CLOSED
if state == false or state == nil then
  state = 'CLOSED'
end

local newState = state

if state == 'HALF_OPEN' then
  -- Any failure in HALF_OPEN → back to OPEN
  newState = 'OPEN'
  failureCount = failureCount + 1
  successCount = 0
elseif state == 'CLOSED' then
  failureCount = failureCount + 1
  if failureCount >= failureThreshold then
    newState = 'OPEN'
  end
  -- OPEN state stays OPEN (transition to HALF_OPEN happens in check)
elseif state == 'OPEN' then
  failureCount = failureCount + 1
end

-- Persist updated state
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
`;

/**
 * RECORD_SUCCESS Lua Script
 *
 * Atomically handles success recording:
 *   HALF_OPEN → CLOSED  if successCount >= successThreshold
 *   CLOSED:              reset failureCount
 *
 * KEYS[1] = zenic:cb:{name}
 * ARGV[1] = failureThreshold
 * ARGV[2] = recoveryTimeoutMs
 * ARGV[3] = successThreshold
 * ARGV[4] = current timestamp (ms)
 * ARGV[5] = TTL for the key (ms)
 *
 * Returns: { newState, failureCount, successCount }
 */
const RECORD_SUCCESS_SCRIPT = `
local key = KEYS[1]
local failureThreshold = tonumber(ARGV[1])
local recoveryTimeoutMs = tonumber(ARGV[2])
local successThreshold = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local ttlMs = tonumber(ARGV[5])

-- Read current state
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

-- Persist updated state
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
`;

/**
 * CHECK Lua Script
 *
 * Atomically checks state and transitions OPEN → HALF_OPEN if recovery
 * timeout has elapsed.
 *
 * KEYS[1] = zenic:cb:{name}
 * ARGV[1] = failureThreshold
 * ARGV[2] = recoveryTimeoutMs
 * ARGV[3] = successThreshold
 * ARGV[4] = current timestamp (ms)
 * ARGV[5] = TTL for the key (ms)
 *
 * Returns: { allowed (0|1), state, retryAfterMs }
 */
const CHECK_SCRIPT = `
local key = KEYS[1]
local failureThreshold = tonumber(ARGV[1])
local recoveryTimeoutMs = tonumber(ARGV[2])
local successThreshold = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local ttlMs = tonumber(ARGV[5])

-- Read current state
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
-- Check if recovery timeout has elapsed
if lastFailureAt > 0 and (now - lastFailureAt) >= recoveryTimeoutMs then
  -- Transition to HALF_OPEN
  redis.call('HMSET', key, 'state', 'HALF_OPEN', 'successCount', 0)
  redis.call('PEXPIRE', key, ttlMs)
  return { 1, 'HALF_OPEN', 0 }
end

-- Still OPEN — calculate retry time
local retryAfterMs = 0
if lastFailureAt > 0 then
  retryAfterMs = math.max(0, recoveryTimeoutMs - (now - lastFailureAt))
end

return { 0, 'OPEN', retryAfterMs }
`;

// ===== IN-MEMORY FALLBACK =====

interface LocalCircuitEntry {
  state: CircuitState;
  failureCount: number;
  successCount: number;
  lastFailureAt: number;
  lastSuccessAt: number;
  config: CircuitBreakerConfig;
}

/** In-memory circuit breaker used as fallback when Redis is unavailable */
class LocalCircuitBreaker {
  private circuits = new Map<string, LocalCircuitEntry>();

  check(name: string, config: CircuitBreakerConfig): CircuitCheckResult {
    let circuit = this.circuits.get(name);
    if (!circuit) {
      circuit = {
        state: "CLOSED",
        failureCount: 0,
        successCount: 0,
        lastFailureAt: 0,
        lastSuccessAt: 0,
        config,
      };
      this.circuits.set(name, circuit);
    }

    const now = Date.now();

    switch (circuit.state) {
      case "CLOSED":
        return { allowed: true, state: "CLOSED", retryAfterMs: 0 };

      case "OPEN": {
        const elapsed = now - circuit.lastFailureAt;
        if (elapsed >= circuit.config.recoveryTimeoutMs) {
          circuit.state = "HALF_OPEN";
          circuit.successCount = 0;
          return { allowed: true, state: "HALF_OPEN", retryAfterMs: 0 };
        }
        const retryAfterMs = circuit.config.recoveryTimeoutMs - elapsed;
        return { allowed: false, state: "OPEN", retryAfterMs };
      }

      case "HALF_OPEN":
        return { allowed: true, state: "HALF_OPEN", retryAfterMs: 0 };
    }
  }

  recordFailure(name: string, config: CircuitBreakerConfig): void {
    let circuit = this.circuits.get(name);
    if (!circuit) {
      circuit = {
        state: "CLOSED",
        failureCount: 0,
        successCount: 0,
        lastFailureAt: 0,
        lastSuccessAt: 0,
        config,
      };
      this.circuits.set(name, circuit);
    }

    circuit.lastFailureAt = Date.now();

    if (circuit.state === "HALF_OPEN") {
      circuit.state = "OPEN";
      circuit.successCount = 0;
      circuit.failureCount++;
    } else if (circuit.state === "CLOSED") {
      circuit.failureCount++;
      if (circuit.failureCount >= config.failureThreshold) {
        circuit.state = "OPEN";
      }
    } else {
      // OPEN — just increment
      circuit.failureCount++;
    }
  }

  recordSuccess(name: string, config: CircuitBreakerConfig): void {
    const circuit = this.circuits.get(name);
    if (!circuit) return;

    circuit.lastSuccessAt = Date.now();

    if (circuit.state === "HALF_OPEN") {
      circuit.successCount++;
      if (circuit.successCount >= config.successThreshold) {
        circuit.state = "CLOSED";
        circuit.failureCount = 0;
        circuit.successCount = 0;
      }
    } else if (circuit.state === "CLOSED") {
      circuit.failureCount = 0;
    }
  }

  reset(name: string): void {
    const circuit = this.circuits.get(name);
    if (!circuit) return;
    circuit.state = "CLOSED";
    circuit.failureCount = 0;
    circuit.successCount = 0;
  }

  getStats(name: string): CircuitBreakerStats | null {
    const circuit = this.circuits.get(name);
    if (!circuit) return null;
    return {
      name,
      state: circuit.state,
      failureCount: circuit.failureCount,
      successCount: circuit.successCount,
      lastFailureAt: circuit.lastFailureAt,
      lastSuccessAt: circuit.lastSuccessAt,
      config: circuit.config,
    };
  }

  getAllStats(): Record<string, CircuitBreakerStats> {
    const result: Record<string, CircuitBreakerStats> = {};
    for (const [name, circuit] of this.circuits) {
      result[name] = {
        name,
        state: circuit.state,
        failureCount: circuit.failureCount,
        successCount: circuit.successCount,
        lastFailureAt: circuit.lastFailureAt,
        lastSuccessAt: circuit.lastSuccessAt,
        config: circuit.config,
      };
    }
    return result;
  }

  getOpenCircuitCount(): number {
    let count = 0;
    for (const circuit of this.circuits.values()) {
      if (circuit.state === "OPEN") count++;
    }
    return count;
  }
}

// ===== UNIFIED CIRCUIT BREAKER =====

/** Configuration for per-circuit overrides */
export interface CircuitBreakerOverrides {
  [name: string]: Partial<CircuitBreakerConfig>;
}

export interface UnifiedCircuitBreakerOptions {
  /** Redis URL (e.g. "redis://localhost:6379") */
  redisUrl: string;
  /** Key prefix (default: "zenic:cb") */
  keyPrefix?: string;
  /** Default config for circuits without specific overrides */
  defaultConfig?: CircuitBreakerConfig;
  /** Per-circuit config overrides */
  overrides?: CircuitBreakerOverrides;
  /** TTL for Redis keys in ms — auto-cleanup of stale state (default: 3600000 = 1h) */
  keyTtlMs?: number;
  /** How long to stay in fallback mode after a Redis error (ms, default: 30000) */
  fallbackCooldownMs?: number;
}

interface FallbackState {
  active: boolean;
  since: number;
  fallbackCount: number;
  lastError: string | null;
}

export class UnifiedCircuitBreaker {
  private redis: Redis | null = null;
  private readonly keyPrefix: string;
  private readonly defaultConfig: CircuitBreakerConfig;
  private readonly overrides: CircuitBreakerOverrides;
  private readonly keyTtlMs: number;
  private readonly fallbackCooldownMs: number;
  private readonly redisUrl: string;

  /** In-memory fallback */
  private readonly localBreaker = new LocalCircuitBreaker();

  /** Fallback state */
  private fallback: FallbackState = {
    active: false,
    since: 0,
    fallbackCount: 0,
    lastError: null,
  };

  /** Whether the Redis connection has been initialized */
  private initialized = false;

  /** Whether Redis is currently connected and available */
  private redisAvailable = false;

  /** Track known circuit names for getAllStats */
  private knownCircuits = new Set<string>();

  constructor(options: UnifiedCircuitBreakerOptions) {
    this.redisUrl = options.redisUrl;
    this.keyPrefix = options.keyPrefix ?? "zenic:cb";
    this.defaultConfig = options.defaultConfig ?? DEFAULT_CB_CONFIG;
    this.overrides = options.overrides ?? {};
    this.keyTtlMs = options.keyTtlMs ?? 3_600_000; // 1 hour default TTL
    this.fallbackCooldownMs = options.fallbackCooldownMs ?? 30_000;
  }

  // ─── Lifecycle ───────────────────────────────────────────────

  /**
   * Initialize the Redis connection. Must be called before first use.
   * If Redis is unavailable, silently falls back to in-memory mode.
   */
  async connect(): Promise<void> {
    if (this.initialized) return;

    try {
      this.redis = new Redis(this.redisUrl, {
        lazyConnect: true,
        maxRetriesPerRequest: 2,
        connectTimeout: 5_000,
        retryStrategy: (times) => {
          if (times > 10) return null;
          return Math.min(times * 200, 3_000);
        },
      });

      this.redis.on("error", (err) => {
        this.handleRedisError(err);
      });

      this.redis.on("close", () => {
        this.redisAvailable = false;
      });

      this.redis.on("ready", () => {
        this.redisAvailable = true;
        if (this.fallback.active) {
          this.fallback.active = false;
        }
      });

      await this.redis.connect();
      this.redisAvailable = true;
      this.initialized = true;
    } catch (err) {
      this.handleRedisError(err);
      this.initialized = true; // Still mark as initialized — operate in fallback
    }
  }

  /**
   * Gracefully close the Redis connection.
   */
  async disconnect(): Promise<void> {
    if (this.redis) {
      this.redisAvailable = false;
      await this.redis.quit().catch(() => {});
      this.redis = null;
    }
  }

  /**
   * Check if Redis is currently available.
   */
  isRedisReady(): boolean {
    return this.redisAvailable && this.redis !== null && this.redis.status === "ready";
  }

  // ─── Core Operations ────────────────────────────────────────

  /**
   * Check if a call is allowed for the given circuit name.
   * Transitions OPEN → HALF_OPEN if recovery timeout has elapsed.
   */
  async check(name: string): Promise<CircuitCheckResult> {
    this.knownCircuits.add(name);
    const config = this.getConfig(name);

    if (!this.isRedisReady()) {
      return this.localBreaker.check(name, config);
    }

    try {
      const now = Date.now();
      const redisKey = `${this.keyPrefix}:${name}`;

      const result = (await this.redis!.eval(
        CHECK_SCRIPT,
        1,
        redisKey,
        String(config.failureThreshold),
        String(config.recoveryTimeoutMs),
        String(config.successThreshold),
        String(now),
        String(this.keyTtlMs),
      )) as [number, string, number];

      const [allowedNum, state, retryAfterMs] = result;
      return {
        allowed: allowedNum === 1,
        state: state as CircuitState,
        retryAfterMs,
      };
    } catch (err) {
      this.handleRedisError(err);
      return this.localBreaker.check(name, config);
    }
  }

  /**
   * Record a successful call. May transition HALF_OPEN → CLOSED.
   */
  async recordSuccess(name: string): Promise<void> {
    this.knownCircuits.add(name);
    const config = this.getConfig(name);

    // Always update local fallback
    this.localBreaker.recordSuccess(name, config);

    if (!this.isRedisReady()) return;

    try {
      const now = Date.now();
      const redisKey = `${this.keyPrefix}:${name}`;

      await this.redis!.eval(
        RECORD_SUCCESS_SCRIPT,
        1,
        redisKey,
        String(config.failureThreshold),
        String(config.recoveryTimeoutMs),
        String(config.successThreshold),
        String(now),
        String(this.keyTtlMs),
      );
    } catch (err) {
      this.handleRedisError(err);
    }
  }

  /**
   * Record a failed call. May transition CLOSED → OPEN or HALF_OPEN → OPEN.
   */
  async recordFailure(name: string): Promise<void> {
    this.knownCircuits.add(name);
    const config = this.getConfig(name);

    // Always update local fallback
    this.localBreaker.recordFailure(name, config);

    if (!this.isRedisReady()) return;

    try {
      const now = Date.now();
      const redisKey = `${this.keyPrefix}:${name}`;

      await this.redis!.eval(
        RECORD_FAILURE_SCRIPT,
        1,
        redisKey,
        String(config.failureThreshold),
        String(config.recoveryTimeoutMs),
        String(config.successThreshold),
        String(now),
        String(this.keyTtlMs),
      );
    } catch (err) {
      this.handleRedisError(err);
    }
  }

  /**
   * Force reset a circuit to CLOSED state.
   */
  async reset(name: string): Promise<void> {
    this.localBreaker.reset(name);

    if (!this.isRedisReady()) return;

    try {
      const redisKey = `${this.keyPrefix}:${name}`;
      await this.redis!.del(redisKey);
    } catch (err) {
      this.handleRedisError(err);
    }
  }

  /**
   * Get stats for a specific circuit. Tries Redis first, falls back to local.
   */
  async getStats(name: string): Promise<CircuitBreakerStats | null> {
    if (!this.isRedisReady()) {
      return this.localBreaker.getStats(name);
    }

    try {
      const redisKey = `${this.keyPrefix}:${name}`;
      const data = await this.redis!.hgetall(redisKey);

      if (!data || !data.state) {
        return null;
      }

      let config = this.getConfig(name);
      if (data.config) {
        try {
          config = JSON.parse(data.config) as CircuitBreakerConfig;
        } catch {
          // Use default config if parse fails
        }
      }

      return {
        name,
        state: data.state as CircuitState,
        failureCount: parseInt(data.failureCount ?? "0", 10),
        successCount: parseInt(data.successCount ?? "0", 10),
        lastFailureAt: parseInt(data.lastFailureAt ?? "0", 10),
        lastSuccessAt: parseInt(data.lastSuccessAt ?? "0", 10),
        config,
      };
    } catch (err) {
      this.handleRedisError(err);
      return this.localBreaker.getStats(name);
    }
  }

  /**
   * Get stats for all known circuits.
   */
  async getAllStats(): Promise<Record<string, CircuitBreakerStats>> {
    if (!this.isRedisReady()) {
      return this.localBreaker.getAllStats();
    }

    try {
      // Scan Redis for all circuit keys
      const pattern = `${this.keyPrefix}:*`;
      const stream = this.redis!.scanStream({ match: pattern, count: 100 });
      const keys: string[] = [];

      await new Promise<void>((resolve, reject) => {
        stream.on("data", (resultKeys: string[]) => {
          keys.push(...resultKeys);
        });
        stream.on("end", resolve);
        stream.on("error", reject);
      });

      const stats: Record<string, CircuitBreakerStats> = {};

      // Include local circuits not yet in Redis
      for (const name of this.knownCircuits) {
        const localStats = this.localBreaker.getStats(name);
        if (localStats) {
          stats[name] = localStats;
        }
      }

      // Override with Redis data where available
      for (const key of keys) {
        const name = key.substring(this.keyPrefix.length + 1);
        const data = await this.redis!.hgetall(key);

        if (data && data.state) {
          let config = this.getConfig(name);
          if (data.config) {
            try {
              config = JSON.parse(data.config) as CircuitBreakerConfig;
            } catch {
              // Use default
            }
          }

          stats[name] = {
            name,
            state: data.state as CircuitState,
            failureCount: parseInt(data.failureCount ?? "0", 10),
            successCount: parseInt(data.successCount ?? "0", 10),
            lastFailureAt: parseInt(data.lastFailureAt ?? "0", 10),
            lastSuccessAt: parseInt(data.lastSuccessAt ?? "0", 10),
            config,
          };
        }
      }

      return stats;
    } catch (err) {
      this.handleRedisError(err);
      return this.localBreaker.getAllStats();
    }
  }

  /**
   * Get the number of open circuits (local count for fast access).
   */
  getOpenCircuitCount(): number {
    return this.localBreaker.getOpenCircuitCount();
  }

  // ─── Config Helpers ─────────────────────────────────────────

  /**
   * Get the effective config for a circuit name, applying overrides.
   */
  getConfig(name: string): CircuitBreakerConfig {
    const override = this.overrides[name];
    if (override) {
      return { ...this.defaultConfig, ...override };
    }
    return { ...this.defaultConfig };
  }

  /**
   * Register or update config override for a circuit name.
   */
  setOverride(name: string, override: Partial<CircuitBreakerConfig>): void {
    this.overrides[name] = { ...this.overrides[name], ...override };
  }

  /**
   * Get the current fallback state.
   */
  getFallbackState(): Readonly<FallbackState> {
    return { ...this.fallback };
  }

  // ─── Error Handling ─────────────────────────────────────────

  private handleRedisError(err: unknown): void {
    const message = err instanceof Error ? err.message : String(err);

    if (!this.fallback.active) {
      this.fallback.active = true;
      this.fallback.since = Date.now();
      this.fallback.fallbackCount++;
    }
    this.fallback.lastError = message;
    this.redisAvailable = false;
  }
}
