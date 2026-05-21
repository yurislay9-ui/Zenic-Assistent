/**
 * #58 Fix: ResourceGovernor — Graceful Degradation Under Pressure
 * 
 * Previous state: Zero protection. The gateway could:
 * - Accept unlimited requests → OOM kill → corrupt SQLite
 * - No rate limiting → one user could flood the API
 * - No concurrency limit → unlimited simultaneous operations
 * - No circuit breaker → keeps retrying failing operations
 * - No memory monitoring → no warning before collapse
 * 
 * This module provides 6 layers of protection:
 * 
 * 1. Rate Limiter — Sliding window per IP + per user (configurable)
 *              → Redis-backed when redisUrl is provided (Phase 2.2)
 * 2. Concurrency Limiter — Max N simultaneous requests
 * 3. Memory Monitor — Reject requests when memory > threshold
 * 4. Circuit Breaker — Stop trying operations that keep failing
 * 5. Graceful Degradation — Simplified responses under pressure
 * 6. DB Health Check — Reject/degrade when DB is under pressure (FASE 1.4)
 */

import { RedisRateLimiter } from "./mcp-gateway/rate-limiter/redis-rate-limiter";
import { UnifiedCircuitBreaker, type CircuitBreakerStats } from "./unified-circuit-breaker";

// ===== TYPES =====

export interface GovernorConfig {
  // Rate limiting
  rateLimitPerMinute: number;       // Max requests per minute per key
  rateLimitBurst: number;           // Burst allowance
  redisUrl?: string;                // Redis URL for distributed rate limiting (optional)
  redisKeyPrefix?: string;          // Key prefix for Redis rate limiter keys
  // Concurrency
  maxConcurrentRequests: number;    // Max simultaneous requests
  // Memory
  memoryWarningPercent: number;     // Warn at this %
  memoryCriticalPercent: number;    // Reject requests at this %
  // Circuit breaker
  circuitFailureThreshold: number;  // Failures before opening circuit
  circuitResetTimeoutMs: number;    // Time before trying again
}

export interface GovernorMetrics {
  // Rate limiter
  totalRequests: number;
  rateLimited: number;
  rateLimiterBackend: 'memory' | 'redis';  // Which backend is active
  // Concurrency
  activeRequests: number;
  maxActiveRequests: number;
  queuedRequests: number;
  // Memory
  memoryUsageMB: number;
  memoryPercent: number;
  memoryStatus: 'normal' | 'warning' | 'critical';
  // Circuit breaker
  circuitsOpen: number;
  circuitBreakerBackend: 'memory' | 'redis';  // Phase 3.2: Which CB backend is active
  // DB Health (FASE 1.4)
  dbStatus: 'healthy' | 'degraded' | 'critical';
  writeQueueLength: number;
  writeLatencyMs: number;
  // Uptime
  uptime: number;
}

export type GovernorVerdict =
  | { allowed: true; pressure: 'none' | 'low' | 'medium' }
  | { allowed: false; reason: string; code: string; retryAfterMs?: number }

// ===== DEFAULT CONFIG =====

const DEFAULT_CONFIG: GovernorConfig = {
  rateLimitPerMinute: 120,        // 120 req/min = 2/sec sustained
  rateLimitBurst: 30,             // Allow 30 extra in burst
  redisUrl: undefined,            // No Redis by default — uses in-memory
  redisKeyPrefix: 'zenic:gov',    // Default key prefix for Redis keys
  maxConcurrentRequests: 50,      // Max 50 simultaneous
  memoryWarningPercent: 85,       // Warn at 85% heap
  memoryCriticalPercent: 99,      // Reject at 99% heap
  circuitFailureThreshold: 5,     // Open after 5 consecutive failures
  circuitResetTimeoutMs: 30000,   // Try again after 30s
}

// ===== SLIDING WINDOW RATE LIMITER =====

interface RateLimitEntry {
  timestamps: number[];  // Sliding window of request timestamps
  burstUsed: number;     // Burst tokens consumed
  burstResetAt: number;  // When burst resets
}

class SlidingWindowRateLimiter {
  private entries = new Map<string, RateLimitEntry>()
  private maxPerMinute: number
  private maxBurst: number

  constructor(maxPerMinute: number, maxBurst: number) {
    this.maxPerMinute = maxPerMinute
    this.maxBurst = maxBurst
  }

  /**
   * Check if a request is allowed for the given key.
   * Returns { allowed, retryAfterMs }
   */
  check(key: string): { allowed: boolean; retryAfterMs: number; remaining: number } {
    const now = Date.now()
    const windowStart = now - 60000 // 1 minute window

    let entry = this.entries.get(key)
    if (!entry) {
      entry = { timestamps: [], burstUsed: 0, burstResetAt: now + 60000 }
      this.entries.set(key, entry)
    }

    // Prune old timestamps outside the window
    entry.timestamps = entry.timestamps.filter(ts => ts > windowStart)

    // Reset burst if window expired
    if (now > entry.burstResetAt) {
      entry.burstUsed = 0
      entry.burstResetAt = now + 60000
    }

    const baseRemaining = this.maxPerMinute - entry.timestamps.length

    // Check if within base limit
    if (baseRemaining > 0) {
      entry.timestamps.push(now)
      return { allowed: true, retryAfterMs: 0, remaining: baseRemaining - 1 }
    }

    // Check burst allowance
    if (entry.burstUsed < this.maxBurst) {
      entry.burstUsed++
      entry.timestamps.push(now)
      return { allowed: true, retryAfterMs: 0, remaining: 0 }
    }

    // Rate limited — calculate when the oldest request in window expires
    const oldestInWindow = entry.timestamps[0]
    const retryAfterMs = oldestInWindow ? (oldestInWindow + 60000) - now : 1000

    return { allowed: false, retryAfterMs: Math.max(retryAfterMs, 1000), remaining: 0 }
  }

  /**
   * Clean up old entries periodically (call every 5 minutes)
   */
  cleanup() {
    const cutoff = Date.now() - 120000 // Remove entries idle for 2+ minutes
    for (const [key, entry] of this.entries) {
      const recent = entry.timestamps.filter(ts => ts > cutoff)
      if (recent.length === 0) {
        this.entries.delete(key)
      } else {
        entry.timestamps = recent
      }
    }
  }
}

// ===== CIRCUIT BREAKER =====

type CircuitState = 'closed' | 'open' | 'half-open'

interface CircuitEntry {
  state: CircuitState
  failureCount: number
  lastFailureAt: number
  lastSuccessAt: number
}

class CircuitBreaker {
  private circuits = new Map<string, CircuitEntry>()
  private failureThreshold: number
  private resetTimeoutMs: number

  constructor(failureThreshold: number, resetTimeoutMs: number) {
    this.failureThreshold = failureThreshold
    this.resetTimeoutMs = resetTimeoutMs
  }

  /**
   * Check if the circuit allows a request through.
   */
  check(key: string): { allowed: boolean; state: CircuitState; retryAfterMs: number } {
    const circuit = this.circuits.get(key)
    if (!circuit) {
      return { allowed: true, state: 'closed', retryAfterMs: 0 }
    }

    const now = Date.now()

    switch (circuit.state) {
      case 'closed':
        return { allowed: true, state: 'closed', retryAfterMs: 0 }

      case 'open': {
        // Check if enough time has passed to try again
        const elapsed = now - circuit.lastFailureAt
        if (elapsed >= this.resetTimeoutMs) {
          circuit.state = 'half-open'
          return { allowed: true, state: 'half-open', retryAfterMs: 0 }
        }
        const retryAfterMs = this.resetTimeoutMs - elapsed
        return { allowed: false, state: 'open', retryAfterMs }
      }

      case 'half-open':
        // Allow one request through to test
        return { allowed: true, state: 'half-open', retryAfterMs: 0 }
    }
  }

  /**
   * Record a success — closes the circuit if it was half-open.
   */
  recordSuccess(key: string) {
    const circuit = this.circuits.get(key)
    if (!circuit) return

    circuit.lastSuccessAt = Date.now()
    circuit.failureCount = 0
    circuit.state = 'closed'
  }

  /**
   * Record a failure — may open the circuit if threshold is reached.
   */
  recordFailure(key: string) {
    let circuit = this.circuits.get(key)
    if (!circuit) {
      circuit = { state: 'closed', failureCount: 0, lastFailureAt: 0, lastSuccessAt: 0 }
      this.circuits.set(key, circuit)
    }

    circuit.failureCount++
    circuit.lastFailureAt = Date.now()

    if (circuit.failureCount >= this.failureThreshold) {
      circuit.state = 'open'
    }
  }

  getOpenCircuitCount(): number {
    let count = 0
    for (const circuit of this.circuits.values()) {
      if (circuit.state === 'open') count++
    }
    return count
  }
}

// ===== MEMORY MONITOR =====

class MemoryMonitor {
  private getConfig: () => { warningPercent: number; criticalPercent: number }

  constructor(getConfig: () => { warningPercent: number; criticalPercent: number }) {
    this.getConfig = getConfig
  }

  getStatus(): { usageMB: number; percent: number; status: 'normal' | 'warning' | 'critical' } {
    const usage = process.memoryUsage()
    const usageMB = Math.round(usage.heapUsed / 1024 / 1024)
    const totalMB = Math.round(usage.heapTotal / 1024 / 1024)
    const percent = totalMB > 0 ? Math.round((usage.heapUsed / usage.heapTotal) * 100) : 0

    const { warningPercent, criticalPercent } = this.getConfig()

    let status: 'normal' | 'warning' | 'critical' = 'normal'
    if (percent >= criticalPercent) {
      status = 'critical'
    } else if (percent >= warningPercent) {
      status = 'warning'
    }

    return { usageMB, percent, status }
  }
}

// ===== CONCURRENCY LIMITER =====

class ConcurrencyLimiter {
  private active = 0
  private maxConcurrent: number
  private maxObserved = 0

  constructor(maxConcurrent: number) {
    this.maxConcurrent = maxConcurrent
  }

  /**
   * Try to acquire a slot. Returns true if allowed.
   */
  tryAcquire(): boolean {
    if (this.active >= this.maxConcurrent) {
      return false
    }
    this.active++
    if (this.active > this.maxObserved) {
      this.maxObserved = this.active
    }
    return true
  }

  /**
   * Release a slot.
   */
  release() {
    if (this.active > 0) {
      this.active--
    }
  }

  getActive(): number { return this.active }
  getMaxObserved(): number { return this.maxObserved }
  getMaxConcurrent(): number { return this.maxConcurrent }
}

// ===== DB HEALTH CHECKER (FASE 1.4) =====

/**
 * #58 Fix + FASE 1.4: DB Health Checker
 * 
 * Monitors write queue length and write latency to detect
 * when SQLite is under pressure. When the DB can't keep up,
 * we reject new requests before they pile up and corrupt data.
 * 
 * Thresholds:
 * - DEGRADED: write latency > 100ms OR queue length > 50
 * - CRITICAL: write latency > 500ms OR queue length > 100
 */
class DBHealthChecker {
  private writeQueueLength: number = 0
  private lastWriteLatencyMs: number = 0
  private lastCheckAt: number = 0
  private dbStatus: 'healthy' | 'degraded' | 'critical' = 'healthy'
  
  // Thresholds
  private readonly DEGRADED_LATENCY_MS = 100     // 100ms write latency = degraded
  private readonly CRITICAL_LATENCY_MS = 500      // 500ms = critical
  private readonly DEGRADED_QUEUE_LENGTH = 50     // 50 queued writes = degraded  
  private readonly CRITICAL_QUEUE_LENGTH = 100    // 100 queued writes = critical
  private readonly CHECK_INTERVAL_MS = 5000       // Check every 5s

  /**
   * Update internal metrics from WriteQueue flush results.
   * Called by WriteQueue after each flush cycle.
   */
  updateMetrics(metrics: { writeQueueLength: number; writeLatencyMs: number }): void {
    this.writeQueueLength = metrics.writeQueueLength
    this.lastWriteLatencyMs = metrics.writeLatencyMs
    this.lastCheckAt = Date.now()

    // Determine status based on thresholds
    // Critical takes precedence over degraded
    if (
      this.lastWriteLatencyMs >= this.CRITICAL_LATENCY_MS ||
      this.writeQueueLength >= this.CRITICAL_QUEUE_LENGTH
    ) {
      this.dbStatus = 'critical'
    } else if (
      this.lastWriteLatencyMs >= this.DEGRADED_LATENCY_MS ||
      this.writeQueueLength >= this.DEGRADED_QUEUE_LENGTH
    ) {
      this.dbStatus = 'degraded'
    } else {
      this.dbStatus = 'healthy'
    }
  }

  /**
   * Get the current DB health status.
   * If no metrics have been received for a while, assume healthy
   * (stale data is better than false positives).
   */
  getStatus(): { status: 'healthy' | 'degraded' | 'critical'; details: string } {
    // If we haven't received metrics in a while, assume healthy
    // (the WriteQueue might not have had any writes)
    const staleThreshold = this.CHECK_INTERVAL_MS * 3 // 15s
    if (this.lastCheckAt > 0 && Date.now() - this.lastCheckAt > staleThreshold) {
      // Only downgrade from critical if data is stale — degraded stays
      if (this.dbStatus === 'critical') {
        return {
          status: 'degraded',
          details: `DB status stale (last update ${Math.round((Date.now() - this.lastCheckAt) / 1000)}s ago). Latency: ${this.lastWriteLatencyMs}ms, Queue: ${this.writeQueueLength}`,
        }
      }
    }

    // No data yet means healthy
    if (this.lastCheckAt === 0) {
      return { status: 'healthy', details: 'No write metrics received yet' }
    }

    const details = `Latency: ${this.lastWriteLatencyMs}ms, Queue: ${this.writeQueueLength}`
    return { status: this.dbStatus, details }
  }

  /**
   * Get the current write queue length.
   */
  getWriteQueueLength(): number {
    return this.writeQueueLength
  }

  /**
   * Get the last write latency in ms.
   */
  getWriteLatencyMs(): number {
    return this.lastWriteLatencyMs
  }
}

// ===== RESOURCE GOVERNOR (Main Class) =====

export class ResourceGovernor {
  private config: GovernorConfig
  private rateLimiter: SlidingWindowRateLimiter
  private redisRateLimiter: RedisRateLimiter | null = null
  private rateLimiterBackend: 'memory' | 'redis' = 'memory'
  private circuitBreaker: CircuitBreaker
  private unifiedCircuitBreaker: UnifiedCircuitBreaker | null = null  // Phase 3.2: Redis-backed unified CB
  private circuitBreakerBackend: 'memory' | 'redis' = 'memory'
  private memoryMonitor: MemoryMonitor
  private concurrencyLimiter: ConcurrencyLimiter
  private dbHealthChecker: DBHealthChecker
  private totalRequests = 0
  private rateLimited = 0
  private startTime = Date.now()
  private cleanupInterval: ReturnType<typeof setInterval> | null = null

  constructor(config: Partial<GovernorConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config }
    this.rateLimiter = new SlidingWindowRateLimiter(
      this.config.rateLimitPerMinute,
      this.config.rateLimitBurst
    )
    this.circuitBreaker = new CircuitBreaker(
      this.config.circuitFailureThreshold,
      this.config.circuitResetTimeoutMs
    )
    this.memoryMonitor = new MemoryMonitor(
      () => ({ warningPercent: this.config.memoryWarningPercent, criticalPercent: this.config.memoryCriticalPercent })
    )
    this.concurrencyLimiter = new ConcurrencyLimiter(
      this.config.maxConcurrentRequests
    )
    this.dbHealthChecker = new DBHealthChecker()

    // Initialize Redis rate limiter if redisUrl is configured
    if (this.config.redisUrl) {
      this.redisRateLimiter = new RedisRateLimiter({
        redisUrl: this.config.redisUrl,
        keyPrefix: this.config.redisKeyPrefix ?? 'zenic:gov',
      })
      // Connect asynchronously — if it fails, the in-memory limiter serves as fallback
      this.redisRateLimiter.connect().then(() => {
        if (this.redisRateLimiter?.isRedisReady()) {
          this.rateLimiterBackend = 'redis'
        }
      }).catch(() => {
        // Redis connection failed — will use in-memory fallback
        this.rateLimiterBackend = 'memory'
      })

      // Phase 3.2: Initialize UnifiedCircuitBreaker for Redis-backed shared state
      this.unifiedCircuitBreaker = new UnifiedCircuitBreaker({
        redisUrl: this.config.redisUrl,
        keyPrefix: 'zenic:cb',
        defaultConfig: {
          failureThreshold: this.config.circuitFailureThreshold,
          recoveryTimeoutMs: this.config.circuitResetTimeoutMs,
          successThreshold: 2,
        },
      })
      this.unifiedCircuitBreaker.connect().then(() => {
        if (this.unifiedCircuitBreaker?.isRedisReady()) {
          this.circuitBreakerBackend = 'redis'
        }
      }).catch(() => {
        // Redis CB connection failed — will use in-memory fallback
        this.circuitBreakerBackend = 'memory'
      })
    }

    // Periodic cleanup of stale rate limit entries
    this.cleanupInterval = setInterval(() => {
      this.rateLimiter.cleanup()
      // Also update backend status from Redis limiter
      if (this.redisRateLimiter) {
        this.rateLimiterBackend = this.redisRateLimiter.isRedisReady() ? 'redis' : 'memory'
      }
      // Phase 3.2: Update circuit breaker backend status
      if (this.unifiedCircuitBreaker) {
        this.circuitBreakerBackend = this.unifiedCircuitBreaker.isRedisReady() ? 'redis' : 'memory'
      }
    }, 300000) // Every 5 minutes
  }

  /**
   * Synchronous check if a request should be allowed.
   * Always uses in-memory rate limiting for zero-latency hot-path checks.
   * For Redis-backed distributed rate limiting, use `checkAsync()` instead.
   * 
   * Check order (by priority):
   * 1. Memory check (prevent OOM)
   * 2. DB health check (prevent DB corruption — FASE 1.4)
   * 3. Circuit breaker check (don't try failing operations)
   * 4. Rate limit check (per IP + per user) — in-memory only
   * 5. Concurrency check
   * 
   * @param ip - Client IP address
   * @param userId - Authenticated user ID (or 'anonymous')
   * @param operationKey - Optional circuit breaker key (e.g., 'db:write', 'mcp:start')
   */
  check(ip: string, userId: string = 'anonymous', operationKey?: string): GovernorVerdict {
    this.totalRequests++

    // 1. Memory check (highest priority — prevent OOM)
    const memStatus = this.memoryMonitor.getStatus()
    if (memStatus.status === 'critical') {
      return {
        allowed: false,
        reason: `Server under memory pressure (${memStatus.percent}% heap). Please retry later.`,
        code: 'MEMORY_PRESSURE',
        retryAfterMs: 10000,
      }
    }

    // 2. DB health check (FASE 1.4 — prevent DB corruption)
    const dbStatus = this.dbHealthChecker.getStatus()
    if (dbStatus.status === 'critical') {
      return {
        allowed: false,
        reason: `Database under pressure: ${dbStatus.details}. Please retry later.`,
        code: 'DB_PRESSURE',
        retryAfterMs: 5000,
      }
    }

    // 3. Circuit breaker check — in-memory only (sync path)
    //    For Redis-backed unified CB, use checkAsync() instead
    if (operationKey) {
      const circuit = this.circuitBreaker.check(operationKey)
      if (!circuit.allowed) {
        return {
          allowed: false,
          reason: `Circuit breaker open for "${operationKey}". Too many recent failures.`,
          code: 'CIRCUIT_OPEN',
          retryAfterMs: circuit.retryAfterMs,
        }
      }
    }

    // 4. Rate limit check — in-memory (per IP + per user)
    const rateLimitResult = this.checkRateLimitSync(ip, userId)
    if (!rateLimitResult.allowed) {
      return rateLimitResult.verdict!
    }

    // 5. Concurrency check
    if (!this.concurrencyLimiter.tryAcquire()) {
      return {
        allowed: false,
        reason: `Too many concurrent requests (${this.concurrencyLimiter.getActive()}/${this.config.maxConcurrentRequests}). Please retry.`,
        code: 'CONCURRENCY_LIMIT',
        retryAfterMs: 2000,
      }
    }

    // Determine pressure level for response headers
    let pressure: 'none' | 'low' | 'medium' = 'none'
    if (memStatus.status === 'warning') {
      pressure = 'medium'
    } else if (dbStatus.status === 'degraded') {
      // FASE 1.4: DB degraded adds medium pressure
      pressure = 'medium'
    } else if (this.concurrencyLimiter.getActive() > this.config.maxConcurrentRequests * 0.7) {
      pressure = 'low'
    }

    return { allowed: true, pressure }
  }

  /**
   * Async check if a request should be allowed.
   * Uses Redis-backed distributed rate limiting when available,
   * falling back to in-memory if Redis is unreachable.
   * 
   * Same check order as `check()`, but step 4 uses Redis when possible.
   * 
   * @param ip - Client IP address
   * @param userId - Authenticated user ID (or 'anonymous')
   * @param operationKey - Optional circuit breaker key (e.g., 'db:write', 'mcp:start')
   */
  async checkAsync(ip: string, userId: string = 'anonymous', operationKey?: string): Promise<GovernorVerdict> {
    this.totalRequests++

    // 1. Memory check (highest priority — prevent OOM)
    const memStatus = this.memoryMonitor.getStatus()
    if (memStatus.status === 'critical') {
      return {
        allowed: false,
        reason: `Server under memory pressure (${memStatus.percent}% heap). Please retry later.`,
        code: 'MEMORY_PRESSURE',
        retryAfterMs: 10000,
      }
    }

    // 2. DB health check (FASE 1.4 — prevent DB corruption)
    const dbStatus = this.dbHealthChecker.getStatus()
    if (dbStatus.status === 'critical') {
      return {
        allowed: false,
        reason: `Database under pressure: ${dbStatus.details}. Please retry later.`,
        code: 'DB_PRESSURE',
        retryAfterMs: 5000,
      }
    }

    // 3. Circuit breaker check (Phase 3.2: use unified CB when Redis available)
    if (operationKey) {
      if (this.unifiedCircuitBreaker?.isRedisReady()) {
        // Use Redis-backed unified circuit breaker (shared with Python)
        const circuit = await this.unifiedCircuitBreaker.check(operationKey)
        if (!circuit.allowed) {
          return {
            allowed: false,
            reason: `Circuit breaker open for "${operationKey}". Too many recent failures.`,
            code: 'CIRCUIT_OPEN',
            retryAfterMs: circuit.retryAfterMs,
          }
        }
      } else {
        // Fall back to local in-memory circuit breaker
        const circuit = this.circuitBreaker.check(operationKey)
        if (!circuit.allowed) {
          return {
            allowed: false,
            reason: `Circuit breaker open for "${operationKey}". Too many recent failures.`,
            code: 'CIRCUIT_OPEN',
            retryAfterMs: circuit.retryAfterMs,
          }
        }
      }
    }

    // 4. Rate limit check — Redis-backed when available
    const rateLimitResult = await this.checkRateLimitAsync(ip, userId)
    if (!rateLimitResult.allowed) {
      return rateLimitResult.verdict!
    }

    // 5. Concurrency check
    if (!this.concurrencyLimiter.tryAcquire()) {
      return {
        allowed: false,
        reason: `Too many concurrent requests (${this.concurrencyLimiter.getActive()}/${this.config.maxConcurrentRequests}). Please retry.`,
        code: 'CONCURRENCY_LIMIT',
        retryAfterMs: 2000,
      }
    }

    // Determine pressure level for response headers
    let pressure: 'none' | 'low' | 'medium' = 'none'
    if (memStatus.status === 'warning') {
      pressure = 'medium'
    } else if (dbStatus.status === 'degraded') {
      pressure = 'medium'
    } else if (this.concurrencyLimiter.getActive() > this.config.maxConcurrentRequests * 0.7) {
      pressure = 'low'
    }

    return { allowed: true, pressure }
  }

  // ─── Rate Limit Helper Methods ─────────────────────────────────

  /**
   * Internal: synchronous rate limit check using in-memory limiter.
   */
  private checkRateLimitSync(
    ip: string,
    userId: string,
  ): { allowed: true } | { allowed: false; verdict: GovernorVerdict } {
    const rateLimitKey = `ip:${ip}`
    const ipCheck = this.rateLimiter.check(rateLimitKey)
    if (!ipCheck.allowed) {
      this.rateLimited++
      return {
        allowed: false,
        verdict: {
          allowed: false,
          reason: `Rate limit exceeded for IP ${ip}. Max ${this.config.rateLimitPerMinute} requests/minute.`,
          code: 'RATE_LIMITED_IP',
          retryAfterMs: ipCheck.retryAfterMs,
        },
      }
    }

    if (userId !== 'anonymous') {
      const userKey = `user:${userId}`
      const userCheck = this.rateLimiter.check(userKey)
      if (!userCheck.allowed) {
        this.rateLimited++
        return {
          allowed: false,
          verdict: {
            allowed: false,
            reason: `Rate limit exceeded for user ${userId}. Max ${this.config.rateLimitPerMinute} requests/minute.`,
            code: 'RATE_LIMITED_USER',
            retryAfterMs: userCheck.retryAfterMs,
          },
        }
      }
    }

    return { allowed: true }
  }

  /**
   * Internal: async rate limit check using Redis-backed limiter when available,
   * falling back to in-memory if Redis is unreachable.
   */
  private async checkRateLimitAsync(
    ip: string,
    userId: string,
  ): Promise<{ allowed: true } | { allowed: false; verdict: GovernorVerdict }> {
    // If Redis rate limiter is available, use it
    if (this.redisRateLimiter?.isRedisReady()) {
      return this.checkRateLimitViaRedis(ip, userId)
    }

    // Fall back to in-memory
    return this.checkRateLimitSync(ip, userId)
  }

  /**
   * Internal: rate limit check via Redis using the MCP RateLimiter interface.
   * The RedisRateLimiter uses sliding window with sorted sets for distributed
   * state, and its own in-memory fallback if Redis drops mid-request.
   */
  private async checkRateLimitViaRedis(
    ip: string,
    userId: string,
  ): Promise<{ allowed: true } | { allowed: false; verdict: GovernorVerdict }> {
    const rateLimitConfig = {
      algorithm: 'sliding_window' as const,
      maxRequests: this.config.rateLimitPerMinute,
      windowMs: 60_000,
      burstSize: this.config.rateLimitBurst,
    }

    // Check IP rate limit via Redis
    const ipResult = await this.redisRateLimiter!.check(
      { toolName: `ip:${ip}` },
      rateLimitConfig,
    )
    if (!ipResult.allowed) {
      this.rateLimited++
      return {
        allowed: false,
        verdict: {
          allowed: false,
          reason: `Rate limit exceeded for IP ${ip}. Max ${this.config.rateLimitPerMinute} requests/minute.`,
          code: 'RATE_LIMITED_IP',
          retryAfterMs: ipResult.retryAfterMs ?? 1000,
        },
      }
    }

    // Check user rate limit via Redis (if authenticated)
    if (userId !== 'anonymous') {
      const userResult = await this.redisRateLimiter!.check(
        { toolName: `user:${userId}` },
        rateLimitConfig,
      )
      if (!userResult.allowed) {
        this.rateLimited++
        return {
          allowed: false,
          verdict: {
            allowed: false,
            reason: `Rate limit exceeded for user ${userId}. Max ${this.config.rateLimitPerMinute} requests/minute.`,
            code: 'RATE_LIMITED_USER',
            retryAfterMs: userResult.retryAfterMs ?? 1000,
          },
        }
      }
    }

    return { allowed: true }
  }

  /**
   * Release a concurrency slot after the request completes.
   */
  release() {
    this.concurrencyLimiter.release()
  }

  /**
   * Record a successful operation (closes circuit breaker).
   * Phase 3.2: Also records to unified CB when Redis is available.
   */
  recordSuccess(operationKey: string) {
    this.circuitBreaker.recordSuccess(operationKey)
    // Also record to unified CB (fire-and-forget, non-blocking)
    if (this.unifiedCircuitBreaker) {
      this.unifiedCircuitBreaker.recordSuccess(operationKey).catch(() => {})
    }
  }

  /**
   * Record a failed operation (may open circuit breaker).
   * Phase 3.2: Also records to unified CB when Redis is available.
   */
  recordFailure(operationKey: string) {
    this.circuitBreaker.recordFailure(operationKey)
    // Also record to unified CB (fire-and-forget, non-blocking)
    if (this.unifiedCircuitBreaker) {
      this.unifiedCircuitBreaker.recordFailure(operationKey).catch(() => {})
    }
  }

  /**
   * Phase 3.2: Get circuit breaker stats for monitoring.
   * Returns stats from the unified (Redis-backed) circuit breaker when available,
   * otherwise returns stats from the local in-memory circuit breaker.
   */
  async getCircuitStats(): Promise<Record<string, CircuitBreakerStats>> {
    if (this.unifiedCircuitBreaker) {
      try {
        return await this.unifiedCircuitBreaker.getAllStats()
      } catch {
        // Fall through to local
      }
    }
    // Return local breaker stats in the same format
    const localStats = (this.circuitBreaker as unknown as { circuits: Map<string, { state: string; failureCount: number; lastFailureAt: number; lastSuccessAt: number }> }).circuits
    const result: Record<string, CircuitBreakerStats> = {}
    if (localStats) {
      for (const [name, entry] of localStats) {
        result[name] = {
          name,
          state: (entry.state === 'closed' ? 'CLOSED' : entry.state === 'open' ? 'OPEN' : 'HALF_OPEN') as CircuitBreakerStats['state'],
          failureCount: entry.failureCount,
          successCount: 0,
          lastFailureAt: entry.lastFailureAt,
          lastSuccessAt: entry.lastSuccessAt,
          config: {
            failureThreshold: this.config.circuitFailureThreshold,
            recoveryTimeoutMs: this.config.circuitResetTimeoutMs,
            successThreshold: 2,
          },
        }
      }
    }
    return result
  }

  /**
   * FASE 1.4: Update DB health metrics from the WriteQueue.
   * Called by WriteQueue after each flush to report latency and queue depth.
   */
  updateDbMetrics(metrics: { writeQueueLength: number; writeLatencyMs: number }): void {
    this.dbHealthChecker.updateMetrics(metrics)
  }

  /**
   * Get current governor metrics for monitoring.
   */
  getMetrics(): GovernorMetrics {
    const memStatus = this.memoryMonitor.getStatus()
    const dbStatus = this.dbHealthChecker.getStatus()

    // Update backend status from Redis limiter if present
    if (this.redisRateLimiter) {
      this.rateLimiterBackend = this.redisRateLimiter.isRedisReady() ? 'redis' : 'memory'
    }

    // Phase 3.2: Update circuit breaker backend status
    if (this.unifiedCircuitBreaker) {
      this.circuitBreakerBackend = this.unifiedCircuitBreaker.isRedisReady() ? 'redis' : 'memory'
    }

    return {
      totalRequests: this.totalRequests,
      rateLimited: this.rateLimited,
      rateLimiterBackend: this.rateLimiterBackend,
      activeRequests: this.concurrencyLimiter.getActive(),
      maxActiveRequests: this.concurrencyLimiter.getMaxObserved(),
      queuedRequests: 0, // We reject instead of queue
      memoryUsageMB: memStatus.usageMB,
      memoryPercent: memStatus.percent,
      memoryStatus: memStatus.status,
      circuitsOpen: this.circuitBreaker.getOpenCircuitCount(),
      circuitBreakerBackend: this.circuitBreakerBackend,  // Phase 3.2
      // FASE 1.4: DB health metrics
      dbStatus: dbStatus.status,
      writeQueueLength: this.dbHealthChecker.getWriteQueueLength(),
      writeLatencyMs: this.dbHealthChecker.getWriteLatencyMs(),
      uptime: Date.now() - this.startTime,
    }
  }

  /**
   * Get the governor configuration.
   */
  getConfig(): GovernorConfig {
    return { ...this.config }
  }

  /**
   * Update governor configuration at runtime.
   * Useful for hot-reload scenarios where the singleton persists.
   */
  updateConfig(updates: Partial<GovernorConfig>) {
    this.config = { ...this.config, ...updates }
  }

  /**
   * Destroy the governor and clean up intervals + Redis connections.
   */
  destroy() {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval)
      this.cleanupInterval = null
    }
    if (this.redisRateLimiter) {
      this.redisRateLimiter.disconnect().catch(() => {})
      this.redisRateLimiter = null
    }
    // Phase 3.2: Clean up unified circuit breaker
    if (this.unifiedCircuitBreaker) {
      this.unifiedCircuitBreaker.disconnect().catch(() => {})
      this.unifiedCircuitBreaker = null
    }
  }
}

// ===== Singleton Instance =====
// Shared across all route handlers in the same process

const globalForGovernor = globalThis as unknown as {
  governor: ResourceGovernor | undefined
}

// In development, always recreate to pick up config changes on hot reload
// In production, reuse the singleton for performance
const devGovernorConfig: GovernorConfig = {
  rateLimitPerMinute: 120,
  rateLimitBurst: 30,
  maxConcurrentRequests: 50,
  memoryWarningPercent: 85,
  memoryCriticalPercent: 99,
  circuitFailureThreshold: 5,
  circuitResetTimeoutMs: 30000,
  // Phase 2.2: Redis-backed distributed rate limiting (optional)
  // Set REDIS_URL env var to enable, e.g. redis://localhost:6379
  redisUrl: process.env.REDIS_URL,
  redisKeyPrefix: process.env.REDIS_KEY_PREFIX ?? 'zenic:gov',
}

export const governor = process.env.NODE_ENV === 'production'
  ? (globalForGovernor.governor ?? new ResourceGovernor(devGovernorConfig))
  : new ResourceGovernor(devGovernorConfig)

if (process.env.NODE_ENV === 'production') globalForGovernor.governor = governor
