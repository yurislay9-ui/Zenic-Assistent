// ─── Zenic-Agents MCP Gateway — Redis-Backed Distributed Rate Limiter ──
// Works across multiple gateway instances by sharing state in Redis.
// Falls back to in-memory rate limiting if Redis is unavailable (graceful degradation).

import Redis from "ioredis";
import {
  RateLimitConfig,
  RateLimitResult,
  RateLimitKey,
  DEFAULT_RATE_LIMIT_CONFIG,
} from "./types";
import { RateLimiter } from "./rate-limiter";
import {
  SLIDING_WINDOW_CHECK,
  FIXED_WINDOW_CHECK,
  TOKEN_BUCKET_CHECK,
} from "./redis-lua-scripts";

/** Configuration options for the Redis rate limiter */
export interface RedisRateLimiterOptions {
  /** Redis connection URL (e.g. "redis://localhost:6379") */
  redisUrl: string;
  /** Key prefix for all Redis keys (default: "zenic:rl") */
  keyPrefix?: string;
  /** How long to stay in fallback mode after a Redis error (ms, default: 30000) */
  fallbackCooldownMs?: number;
  /** Maximum number of retries for Redis commands (default: 2) */
  maxRetries?: number;
  /** Redis key TTL buffer added on top of windowMs (default: 5000) */
  ttlBufferMs?: number;
}

interface FallbackState {
  /** Whether we are currently using the in-memory fallback */
  active: boolean;
  /** Timestamp when we entered fallback mode */
  since: number;
  /** Total number of times we fell back to memory */
  fallbackCount: number;
  /** Last error that triggered fallback */
  lastError: string | null;
}

export class RedisRateLimiter {
  private redis: Redis | null = null;
  private readonly keyPrefix: string;
  private readonly fallbackCooldownMs: number;
  private readonly maxRetries: number;
  private readonly ttlBufferMs: number;
  private readonly redisUrl: string;

  /** In-memory fallback used when Redis is unavailable */
  private readonly memoryLimiter = new RateLimiter();

  /** Current fallback state */
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

  /** Registered configs — mirrored in the memory fallback */
  private configs = new Map<string, RateLimitConfig>();

  /** Counter for generating unique request IDs */
  private requestIdCounter = 0;

  constructor(options: RedisRateLimiterOptions) {
    this.redisUrl = options.redisUrl;
    this.keyPrefix = options.keyPrefix ?? "zenic:rl";
    this.fallbackCooldownMs = options.fallbackCooldownMs ?? 30_000;
    this.maxRetries = options.maxRetries ?? 2;
    this.ttlBufferMs = options.ttlBufferMs ?? 5_000;
  }

  // ─── Lifecycle ───────────────────────────────────────────────────

  /**
   * Initialize the Redis connection. Must be called before first use.
   * If Redis is unavailable, silently falls back to in-memory mode.
   */
  async connect(): Promise<void> {
    if (this.initialized) return;

    try {
      this.redis = new Redis(this.redisUrl, {
        lazyConnect: true,
        maxRetriesPerRequest: this.maxRetries,
        connectTimeout: 5_000,
        retryStrategy: (times) => {
          // Stop retrying after 10 attempts; we'll fall back to memory
          if (times > 10) return null;
          return Math.min(times * 200, 3_000);
        },
      });

      // Attach event handlers before connecting
      this.redis.on("error", (err) => {
        this.handleRedisError(err);
      });

      this.redis.on("close", () => {
        this.redisAvailable = false;
      });

      this.redis.on("ready", () => {
        this.redisAvailable = true;
        // If we were in fallback mode, try recovering
        if (this.fallback.active) {
          this.fallback.active = false;
        }
      });

      await this.redis.connect();

      // Load Lua scripts
      await this.loadScripts();

      this.redisAvailable = true;
      this.initialized = true;
    } catch (err) {
      this.handleRedisError(err);
      this.initialized = true; // Still mark as initialized so we can operate in fallback
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

  // ─── Config Registration ─────────────────────────────────────────

  /** Register rate-limit config for a key */
  registerConfig(key: string, config: RateLimitConfig): void {
    this.configs.set(key, config);
    this.memoryLimiter.registerConfig(key, config);
  }

  /** Remove a registered config */
  unregisterConfig(key: string): boolean {
    this.configs.delete(key);
    return this.memoryLimiter.unregisterConfig(key);
  }

  /** Retrieve a registered config */
  getConfig(key: string): RateLimitConfig | undefined {
    return this.configs.get(key);
  }

  // ─── Core Operations ─────────────────────────────────────────────

  /** Check if a request is allowed — consumes a slot if so */
  async check(
    key: RateLimitKey,
    configOverride?: RateLimitConfig,
  ): Promise<RateLimitResult> {
    const configKey = this.buildConfigKey(key);
    const config =
      configOverride ??
      this.configs.get(configKey) ??
      this.configs.get(key.toolName) ??
      DEFAULT_RATE_LIMIT_CONFIG;

    // If Redis is not available, fall back to in-memory
    if (!this.isRedisReady()) {
      return this.fallbackCheck(key, configOverride);
    }

    try {
      switch (config.algorithm) {
        case "token_bucket":
          return await this.tokenBucketCheck(configKey, config);
        case "sliding_window":
          return await this.slidingWindowCheck(configKey, config);
        case "fixed_window":
          return await this.fixedWindowCheck(configKey, config);
        default:
          return await this.slidingWindowCheck(configKey, config);
      }
    } catch (err) {
      this.handleRedisError(err);
      return this.fallbackCheck(key, configOverride);
    }
  }

  /** Synchronous check — always uses in-memory fallback.
   *  Use the async `check()` for Redis-backed operations. */
  checkSync(
    key: RateLimitKey,
    configOverride?: RateLimitConfig,
  ): RateLimitResult {
    return this.memoryLimiter.check(key, configOverride);
  }

  /** Reset rate-limit state for a key */
  async reset(key: RateLimitKey): Promise<void> {
    const configKey = this.buildConfigKey(key);

    // Always reset in-memory
    this.memoryLimiter.reset(key);

    if (!this.isRedisReady()) return;

    try {
      const patterns = [
        `${this.keyPrefix}:sw:${configKey}`,
        `${this.keyPrefix}:fw:${configKey}:*`,
        `${this.keyPrefix}:tb:${configKey}`,
      ];

      // Delete direct keys
      for (const pattern of patterns) {
        if (pattern.endsWith("*")) {
          // Wildcard: scan and delete
          const stream = this.redis!.scanStream({
            match: pattern,
            count: 100,
          });
          const keys: string[] = [];
          stream.on("data", (resultKeys: string[]) => {
            keys.push(...resultKeys);
          });
          await new Promise<void>((resolve, reject) => {
            stream.on("end", async () => {
              if (keys.length > 0) {
                await this.redis!.del(...keys);
              }
              resolve();
            });
            stream.on("error", reject);
          });
        } else {
          await this.redis!.del(pattern);
        }
      }
    } catch (err) {
      this.handleRedisError(err);
    }
  }

  /** Peek at current status without consuming a slot */
  async peek(
    key: RateLimitKey,
    configOverride?: RateLimitConfig,
  ): Promise<Omit<RateLimitResult, "allowed" | "consumed">> {
    const configKey = this.buildConfigKey(key);
    const config =
      configOverride ??
      this.configs.get(configKey) ??
      this.configs.get(key.toolName) ??
      DEFAULT_RATE_LIMIT_CONFIG;

    if (!this.isRedisReady()) {
      return this.memoryLimiter.peek(key, configOverride);
    }

    try {
      switch (config.algorithm) {
        case "token_bucket":
          return await this.tokenBucketPeek(configKey, config);
        case "sliding_window":
          return await this.slidingWindowPeek(configKey, config);
        case "fixed_window":
          return await this.fixedWindowPeek(configKey, config);
        default:
          return await this.slidingWindowPeek(configKey, config);
      }
    } catch (err) {
      this.handleRedisError(err);
      return this.memoryLimiter.peek(key, configOverride);
    }
  }

  // ─── Housekeeping ────────────────────────────────────────────────

  /** Remove stale entries. Redis keys auto-expire, but we still
   *  clean up the in-memory fallback. */
  cleanup(): { bucketsRemoved: number; windowsRemoved: number } {
    return this.memoryLimiter.cleanup();
  }

  /** Get internal stats for monitoring / debugging */
  getStats(): {
    registeredConfigs: number;
    activeBuckets: number;
    activeWindows: number;
    redisAvailable: boolean;
    fallbackActive: boolean;
    fallbackCount: number;
    backend: "redis" | "memory";
  } {
    const memStats = this.memoryLimiter.getStats();
    return {
      registeredConfigs: memStats.registeredConfigs,
      activeBuckets: memStats.activeBuckets,
      activeWindows: memStats.activeWindows,
      redisAvailable: this.redisAvailable,
      fallbackActive: this.fallback.active,
      fallbackCount: this.fallback.fallbackCount,
      backend: this.isRedisReady() ? "redis" : "memory",
    };
  }

  /**
   * Check if Redis is currently available.
   */
  isRedisReady(): boolean {
    return this.redisAvailable && this.redis !== null && this.redis.status === "ready";
  }

  /**
   * Get the current fallback state.
   */
  getFallbackState(): Readonly<FallbackState> {
    return { ...this.fallback };
  }

  // ─── Algorithm Implementations (Redis) ───────────────────────────

  private async slidingWindowCheck(
    configKey: string,
    config: RateLimitConfig,
  ): Promise<RateLimitResult> {
    const now = Date.now();
    const windowStart = now - config.windowMs;
    const redisKey = `${this.keyPrefix}:sw:${configKey}`;
    const memberId = `${now}:${this.nextRequestId()}`;
    const ttlMs = config.windowMs + this.ttlBufferMs;

    const result = await this.redis!.eval(
      SLIDING_WINDOW_CHECK,
      1,
      redisKey,
      String(windowStart),
      String(now),
      memberId,
      String(config.maxRequests),
      String(ttlMs),
    ) as [number, number, number, number];

    const [allowed, _count, remaining, resetAt] = result;

    if (allowed) {
      return {
        allowed: true,
        remaining,
        resetAt,
        limit: config.maxRequests,
        consumed: 1,
      };
    }

    const retryAfterMs = Math.max(1, resetAt + config.windowMs - now);
    return {
      allowed: false,
      remaining: 0,
      resetAt: resetAt + config.windowMs,
      retryAfterMs,
      limit: config.maxRequests,
      consumed: 0,
    };
  }

  private async fixedWindowCheck(
    configKey: string,
    config: RateLimitConfig,
  ): Promise<RateLimitResult> {
    const now = Date.now();
    const windowIndex = Math.floor(now / config.windowMs);
    const redisKey = `${this.keyPrefix}:fw:${configKey}:${windowIndex}`;
    const ttlMs = config.windowMs + this.ttlBufferMs;
    const resetAt = (windowIndex + 1) * config.windowMs;

    const result = await this.redis!.eval(
      FIXED_WINDOW_CHECK,
      1,
      redisKey,
      String(config.maxRequests),
      String(ttlMs),
      String(resetAt),
    ) as [number, number, number, number];

    const [allowed, _count, remaining, _resetAt] = result;

    if (allowed) {
      return {
        allowed: true,
        remaining,
        resetAt,
        limit: config.maxRequests,
        consumed: 1,
      };
    }

    return {
      allowed: false,
      remaining: 0,
      resetAt,
      retryAfterMs: Math.max(1, resetAt - now),
      limit: config.maxRequests,
      consumed: 0,
    };
  }

  private async tokenBucketCheck(
    configKey: string,
    config: RateLimitConfig,
  ): Promise<RateLimitResult> {
    const now = Date.now();
    const redisKey = `${this.keyPrefix}:tb:${configKey}`;
    const maxTokens = config.burstSize ?? config.maxRequests;
    const refillRatePerMs =
      (config.refillRate ?? config.maxRequests) / config.windowMs;
    const ttlMs = config.windowMs * 2 + this.ttlBufferMs;

    const result = await this.redis!.eval(
      TOKEN_BUCKET_CHECK,
      1,
      redisKey,
      String(now),
      String(maxTokens),
      String(refillRatePerMs),
      String(ttlMs),
    ) as [number, number, number, number];

    const [allowed, tokensRemaining, resetAt, limit] = result;

    if (allowed) {
      return {
        allowed: true,
        remaining: tokensRemaining,
        resetAt,
        limit,
        consumed: 1,
      };
    }

    const retryAfterMs = Math.max(1, resetAt - now);
    return {
      allowed: false,
      remaining: 0,
      resetAt,
      retryAfterMs,
      limit,
      consumed: 0,
    };
  }

  // ─── Peek Implementations (Redis) ────────────────────────────────

  private async slidingWindowPeek(
    configKey: string,
    config: RateLimitConfig,
  ): Promise<Omit<RateLimitResult, "allowed" | "consumed">> {
    const now = Date.now();
    const windowStart = now - config.windowMs;
    const redisKey = `${this.keyPrefix}:sw:${configKey}`;

    // Prune old entries and count
    await this.redis!.zremrangebyscore(redisKey, "-inf", windowStart);
    const count = await this.redis!.zcard(redisKey);

    const remaining = Math.max(0, config.maxRequests - count);

    // Find the earliest entry for resetAt
    const earliest = await this.redis!.zrange(redisKey, 0, 0, "WITHSCORES");
    const resetAt =
      earliest.length >= 2
        ? Number(earliest[1]) + config.windowMs
        : now + config.windowMs;

    return { remaining, resetAt, limit: config.maxRequests };
  }

  private async fixedWindowPeek(
    configKey: string,
    config: RateLimitConfig,
  ): Promise<Omit<RateLimitResult, "allowed" | "consumed">> {
    const now = Date.now();
    const windowIndex = Math.floor(now / config.windowMs);
    const redisKey = `${this.keyPrefix}:fw:${configKey}:${windowIndex}`;
    const resetAt = (windowIndex + 1) * config.windowMs;

    const count = await this.redis!.get(redisKey);
    const currentCount = count ? parseInt(count, 10) : 0;

    return {
      remaining: Math.max(0, config.maxRequests - currentCount),
      resetAt,
      limit: config.maxRequests,
    };
  }

  private async tokenBucketPeek(
    configKey: string,
    config: RateLimitConfig,
  ): Promise<Omit<RateLimitResult, "allowed" | "consumed">> {
    const now = Date.now();
    const redisKey = `${this.keyPrefix}:tb:${configKey}`;
    const maxTokens = config.burstSize ?? config.maxRequests;
    const refillRatePerMs =
      (config.refillRate ?? config.maxRequests) / config.windowMs;

    const data = await this.redis!.hmget(redisKey, "tokens", "lastRefill");

    if (data[0] == null || data[1] == null) {
      // No bucket exists yet — full capacity
      return {
        remaining: maxTokens,
        resetAt: now + config.windowMs,
        limit: maxTokens,
      };
    }

    const tokens = parseFloat(data[0]!);
    const lastRefill = parseFloat(data[1]!);

    // Simulate refill without mutating
    const elapsed = now - lastRefill;
    const currentTokens = Math.min(maxTokens, tokens + elapsed * refillRatePerMs);
    const resetAt =
      refillRatePerMs > 0
        ? now + Math.ceil((maxTokens - currentTokens) / refillRatePerMs)
        : now + config.windowMs;

    return {
      remaining: Math.floor(currentTokens),
      resetAt,
      limit: maxTokens,
    };
  }

  // ─── Fallback & Error Handling ───────────────────────────────────

  private fallbackCheck(
    key: RateLimitKey,
    configOverride?: RateLimitConfig,
  ): RateLimitResult {
    if (!this.fallback.active) {
      this.fallback.active = true;
      this.fallback.since = Date.now();
      this.fallback.fallbackCount++;
    }
    return this.memoryLimiter.check(key, configOverride);
  }

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

  // ─── Script Loading ──────────────────────────────────────────────

  private async loadScripts(): Promise<void> {
    if (!this.redis) return;

    // Pre-load Lua scripts using EVALSHA-friendly approach.
    // ioredis automatically uses EVALSHA after the first EVAL,
    // so we just need to run each script once to cache it.
    try {
      // Test run with dummy key to load the script into Redis cache
      const testKey = `${this.keyPrefix}:_init:test`;

      await this.redis
        .eval(SLIDING_WINDOW_CHECK, 1, testKey, "0", "1", "init", "1", "60000")
        .catch(() => {});
      await this.redis
        .eval(FIXED_WINDOW_CHECK, 1, testKey, "1", "60000", "60000")
        .catch(() => {});
      await this.redis
        .eval(TOKEN_BUCKET_CHECK, 1, testKey, "1", "1", "0.001", "120000")
        .catch(() => {});

      // Clean up test key
      await this.redis.del(testKey).catch(() => {});
    } catch {
      // Script loading failure is not critical — scripts will be loaded on first use
    }
  }

  // ─── Helpers ─────────────────────────────────────────────────────

  private buildConfigKey(key: RateLimitKey): string {
    return [key.toolName, key.tenantId ?? "*", key.executorId ?? "*"].join(":");
  }

  private nextRequestId(): number {
    return ++this.requestIdCounter;
  }
}
