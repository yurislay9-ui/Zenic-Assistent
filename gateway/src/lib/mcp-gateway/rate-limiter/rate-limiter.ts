// ─── Zenic-Agents MCP Gateway — Rate Limiter Service ──────────────────
// Strategy Pattern: pluggable rate-limiting algorithms
// All in-memory for hot-path performance (no DB)

import {
  RateLimitConfig,
  RateLimitResult,
  TokenBucketState,
  RateLimitKey,
  DEFAULT_RATE_LIMIT_CONFIG,
} from "./types";

/**
 * In-memory rate limiter supporting three algorithms:
 *
 * 1. **Token Bucket** — best for bursty traffic. Tokens refill at a constant
 *    rate; each request consumes one token. Allows short bursts up to the
 *    bucket capacity.
 *
 * 2. **Sliding Window** — best for smooth rate limiting. Tracks exact
 *    timestamps of recent requests within the window for precise accounting.
 *
 * 3. **Fixed Window** — simplest algorithm. Groups requests into fixed time
 *    periods and counts against a per-period cap.
 */
export class RateLimiter {
  private buckets = new Map<string, TokenBucketState>();
  private windows = new Map<string, number[]>();
  private configs = new Map<string, RateLimitConfig>();

  // ─── Config Registration ──────────────────────────────────────────

  /** Register rate-limit config for a tool (or tool+tenant+executor) */
  registerConfig(key: string, config: RateLimitConfig): void {
    this.configs.set(key, config);
  }

  /** Remove a registered config */
  unregisterConfig(key: string): boolean {
    return this.configs.delete(key);
  }

  /** Retrieve a registered config */
  getConfig(key: string): RateLimitConfig | undefined {
    return this.configs.get(key);
  }

  // ─── Core Operations ──────────────────────────────────────────────

  /** Check if a request is allowed — consumes a slot if so */
  check(key: RateLimitKey, configOverride?: RateLimitConfig): RateLimitResult {
    const configKey = this.buildConfigKey(key);
    const config =
      configOverride ??
      this.configs.get(configKey) ??
      this.configs.get(key.toolName) ??
      DEFAULT_RATE_LIMIT_CONFIG;

    switch (config.algorithm) {
      case "token_bucket":
        return this.tokenBucketCheck(configKey, config);
      case "sliding_window":
        return this.slidingWindowCheck(configKey, config);
      case "fixed_window":
        return this.fixedWindowCheck(configKey, config);
      default:
        return this.tokenBucketCheck(configKey, config);
    }
  }

  /** Reset rate-limit state for a key (e.g. after admin override) */
  reset(key: RateLimitKey): void {
    const configKey = this.buildConfigKey(key);
    this.buckets.delete(configKey);
    this.windows.delete(configKey);
    // Also clean up fixed-window keys that share the prefix
    for (const mapKey of this.windows.keys()) {
      if (mapKey.startsWith(configKey + ":")) {
        this.windows.delete(mapKey);
      }
    }
  }

  /** Peek at current status without consuming a slot */
  peek(
    key: RateLimitKey,
    configOverride?: RateLimitConfig,
  ): Omit<RateLimitResult, "allowed" | "consumed"> {
    const configKey = this.buildConfigKey(key);
    const config =
      configOverride ??
      this.configs.get(configKey) ??
      this.configs.get(key.toolName) ??
      DEFAULT_RATE_LIMIT_CONFIG;

    switch (config.algorithm) {
      case "token_bucket":
        return this.tokenBucketPeek(configKey, config);
      case "sliding_window":
        return this.slidingWindowPeek(configKey, config);
      case "fixed_window":
        return this.fixedWindowPeek(configKey, config);
      default:
        return this.tokenBucketPeek(configKey, config);
    }
  }

  // ─── Token Bucket Algorithm ───────────────────────────────────────

  private tokenBucketCheck(
    key: string,
    config: RateLimitConfig,
  ): RateLimitResult {
    const now = Date.now();
    let bucket = this.buckets.get(key);

    if (!bucket) {
      const maxTokens = config.burstSize ?? config.maxRequests;
      const refillRatePerMs =
        (config.refillRate ?? config.maxRequests) / config.windowMs;
      bucket = {
        tokens: maxTokens,
        lastRefill: now,
        maxTokens,
        refillRatePerMs,
      };
      this.buckets.set(key, bucket);
    }

    // Refill tokens based on elapsed time
    this.refillBucket(bucket, now);

    // Try to consume a token
    if (bucket.tokens >= 1) {
      bucket.tokens -= 1;
      return {
        allowed: true,
        remaining: Math.floor(bucket.tokens),
        resetAt:
          now +
          Math.ceil(
            (bucket.maxTokens - bucket.tokens) / bucket.refillRatePerMs,
          ),
        limit: bucket.maxTokens,
        consumed: 1,
      };
    }

    // Rate limit exceeded
    const retryAfterMs = Math.ceil(
      (1 - bucket.tokens) / bucket.refillRatePerMs,
    );
    return {
      allowed: false,
      remaining: 0,
      resetAt: now + retryAfterMs,
      retryAfterMs,
      limit: bucket.maxTokens,
      consumed: 0,
    };
  }

  private tokenBucketPeek(
    key: string,
    config: RateLimitConfig,
  ): Omit<RateLimitResult, "allowed" | "consumed"> {
    const now = Date.now();
    let bucket = this.buckets.get(key);

    if (!bucket) {
      const maxTokens = config.burstSize ?? config.maxRequests;
      const refillRatePerMs =
        (config.refillRate ?? config.maxRequests) / config.windowMs;
      return {
        remaining: maxTokens,
        resetAt: now + config.windowMs,
        limit: maxTokens,
      };
    }

    // Simulate refill without mutating
    const elapsed = now - bucket.lastRefill;
    const tokensToAdd = elapsed * bucket.refillRatePerMs;
    const currentTokens = Math.min(bucket.maxTokens, bucket.tokens + tokensToAdd);

    return {
      remaining: Math.floor(currentTokens),
      resetAt:
        now +
        Math.ceil(
          (bucket.maxTokens - currentTokens) / bucket.refillRatePerMs,
        ),
      limit: bucket.maxTokens,
    };
  }

  /** Refill bucket tokens based on elapsed time (mutates state) */
  private refillBucket(bucket: TokenBucketState, now: number): void {
    const elapsed = now - bucket.lastRefill;
    if (elapsed > 0) {
      const tokensToAdd = elapsed * bucket.refillRatePerMs;
      bucket.tokens = Math.min(bucket.maxTokens, bucket.tokens + tokensToAdd);
      bucket.lastRefill = now;
    }
  }

  // ─── Sliding Window Algorithm ─────────────────────────────────────

  private slidingWindowCheck(
    key: string,
    config: RateLimitConfig,
  ): RateLimitResult {
    const now = Date.now();
    const windowStart = now - config.windowMs;
    let window = this.windows.get(key) ?? [];

    // Prune entries outside the window
    window = window.filter((ts) => ts > windowStart);

    if (window.length < config.maxRequests) {
      window.push(now);
      this.windows.set(key, window);
      return {
        allowed: true,
        remaining: config.maxRequests - window.length,
        resetAt:
          window.length > 0
            ? window[0] + config.windowMs
            : now + config.windowMs,
        limit: config.maxRequests,
        consumed: 1,
      };
    }

    // Rate limit exceeded
    const oldestInWindow = window[0] ?? now;
    const retryAfterMs = Math.max(1, oldestInWindow + config.windowMs - now);
    this.windows.set(key, window);
    return {
      allowed: false,
      remaining: 0,
      resetAt: oldestInWindow + config.windowMs,
      retryAfterMs,
      limit: config.maxRequests,
      consumed: 0,
    };
  }

  private slidingWindowPeek(
    key: string,
    config: RateLimitConfig,
  ): Omit<RateLimitResult, "allowed" | "consumed"> {
    const now = Date.now();
    const windowStart = now - config.windowMs;
    const window = (this.windows.get(key) ?? []).filter(
      (ts) => ts > windowStart,
    );

    const remaining = Math.max(0, config.maxRequests - window.length);
    const resetAt =
      window.length > 0
        ? window[0] + config.windowMs
        : now + config.windowMs;

    return {
      remaining,
      resetAt,
      limit: config.maxRequests,
    };
  }

  // ─── Fixed Window Algorithm ───────────────────────────────────────

  private fixedWindowCheck(
    key: string,
    config: RateLimitConfig,
  ): RateLimitResult {
    const now = Date.now();
    const windowIndex = Math.floor(now / config.windowMs);
    const windowKey = `${key}:${windowIndex}`;
    let window = this.windows.get(windowKey) ?? [];

    if (window.length < config.maxRequests) {
      window.push(now);
      this.windows.set(windowKey, window);
      const resetAt = (windowIndex + 1) * config.windowMs;
      return {
        allowed: true,
        remaining: config.maxRequests - window.length,
        resetAt,
        limit: config.maxRequests,
        consumed: 1,
      };
    }

    // Rate limit exceeded
    const resetAt = (windowIndex + 1) * config.windowMs;
    return {
      allowed: false,
      remaining: 0,
      resetAt,
      retryAfterMs: Math.max(1, resetAt - now),
      limit: config.maxRequests,
      consumed: 0,
    };
  }

  private fixedWindowPeek(
    key: string,
    config: RateLimitConfig,
  ): Omit<RateLimitResult, "allowed" | "consumed"> {
    const now = Date.now();
    const windowIndex = Math.floor(now / config.windowMs);
    const windowKey = `${key}:${windowIndex}`;
    const window = this.windows.get(windowKey) ?? [];
    const resetAt = (windowIndex + 1) * config.windowMs;

    return {
      remaining: Math.max(0, config.maxRequests - window.length),
      resetAt,
      limit: config.maxRequests,
    };
  }

  // ─── Housekeeping ─────────────────────────────────────────────────

  /** Remove stale entries to prevent unbounded memory growth.
   *  Call periodically (e.g. every 60s) from a timer or cron. */
  cleanup(): { bucketsRemoved: number; windowsRemoved: number } {
    const now = Date.now();
    let bucketsRemoved = 0;
    let windowsRemoved = 0;

    // Remove expired buckets — those whose tokens are full and haven't been
    // used recently (lastRefill > 2× the largest window)
    for (const [key, bucket] of this.buckets.entries()) {
      if (
        bucket.tokens >= bucket.maxTokens &&
        now - bucket.lastRefill > 120_000 // 2 minutes idle
      ) {
        this.buckets.delete(key);
        bucketsRemoved++;
      }
    }

    // Remove expired windows — any window whose entries are all stale
    for (const [key, entries] of this.windows.entries()) {
      if (entries.length === 0 || entries[entries.length - 1] < now - 120_000) {
        this.windows.delete(key);
        windowsRemoved++;
      }
    }

    return { bucketsRemoved, windowsRemoved };
  }

  /** Get internal stats for monitoring / debugging */
  getStats(): {
    registeredConfigs: number;
    activeBuckets: number;
    activeWindows: number;
  } {
    return {
      registeredConfigs: this.configs.size,
      activeBuckets: this.buckets.size,
      activeWindows: this.windows.size,
    };
  }

  // ─── Helpers ──────────────────────────────────────────────────────

  private buildConfigKey(key: RateLimitKey): string {
    return [key.toolName, key.tenantId ?? "*", key.executorId ?? "*"].join(
      ":",
    );
  }
}
