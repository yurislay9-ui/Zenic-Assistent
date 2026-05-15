// ─── Zenic-Agents MCP Gateway — Rate Limiter Type System ──────────────
// Strategy Pattern: pluggable rate-limiting algorithms
// All in-memory for hot-path performance (no DB)

/** Rate limiting algorithm types */
export type RateLimitAlgorithm = "token_bucket" | "sliding_window" | "fixed_window";

/** Rate limit configuration per tool/tenant */
export interface RateLimitConfig {
  /** Algorithm to use */
  algorithm: RateLimitAlgorithm;
  /** Maximum requests allowed within the window */
  maxRequests: number;
  /** Time window in milliseconds */
  windowMs: number;
  /** Burst capacity (for token bucket) — defaults to maxRequests */
  burstSize?: number;
  /** Refill rate per second (for token bucket) — defaults to maxRequests / (windowMs / 1000) */
  refillRate?: number;
}

/** Rate limit check result */
export interface RateLimitResult {
  /** Whether the request is allowed */
  allowed: boolean;
  /** Remaining capacity after this check */
  remaining: number;
  /** Epoch ms when the limit resets */
  resetAt: number;
  /** Milliseconds until the caller should retry (only set when allowed=false) */
  retryAfterMs?: number;
  /** Maximum limit for this window */
  limit: number;
  /** Number of tokens/requests consumed by this check (0 when denied) */
  consumed: number;
}

/** Internal bucket state for token-bucket algorithm */
export interface TokenBucketState {
  /** Current number of available tokens */
  tokens: number;
  /** Last refill timestamp (epoch ms) */
  lastRefill: number;
  /** Maximum token capacity */
  maxTokens: number;
  /** Tokens refilled per millisecond */
  refillRatePerMs: number;
}

/** Internal sliding-window entry — a single request timestamp */
export interface SlidingWindowEntry {
  /** Epoch ms when the request occurred */
  timestamp: number;
}

/** Rate limit key structure — uniquely identifies a rate-limit scope */
export interface RateLimitKey {
  /** Tool name being rate-limited */
  toolName: string;
  /** Optional tenant scope */
  tenantId?: string;
  /** Optional executor scope */
  executorId?: string;
}

/** Default rate-limit configuration — used when no config is registered */
export const DEFAULT_RATE_LIMIT_CONFIG: RateLimitConfig = {
  algorithm: "sliding_window",
  maxRequests: 100,
  windowMs: 60_000, // 1 minute
};
