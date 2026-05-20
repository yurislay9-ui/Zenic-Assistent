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
 * This module provides 5 layers of protection:
 * 
 * 1. Rate Limiter — Sliding window per IP + per user (configurable)
 * 2. Concurrency Limiter — Max N simultaneous requests
 * 3. Memory Monitor — Reject requests when memory > threshold
 * 4. Circuit Breaker — Stop trying operations that keep failing
 * 5. Graceful Degradation — Simplified responses under pressure
 */

// ===== TYPES =====

export interface GovernorConfig {
  // Rate limiting
  rateLimitPerMinute: number;       // Max requests per minute per key
  rateLimitBurst: number;           // Burst allowance
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

// ===== RESOURCE GOVERNOR (Main Class) =====

export class ResourceGovernor {
  private config: GovernorConfig
  private rateLimiter: SlidingWindowRateLimiter
  private circuitBreaker: CircuitBreaker
  private memoryMonitor: MemoryMonitor
  private concurrencyLimiter: ConcurrencyLimiter
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

    // Periodic cleanup of stale rate limit entries
    this.cleanupInterval = setInterval(() => {
      this.rateLimiter.cleanup()
    }, 300000) // Every 5 minutes
  }

  /**
   * Check if a request should be allowed.
   * This is the main entry point for the middleware.
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

    // 2. Circuit breaker check (don't try failing operations)
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

    // 3. Rate limit check (per IP + per user)
    const rateLimitKey = `ip:${ip}`
    const ipCheck = this.rateLimiter.check(rateLimitKey)
    if (!ipCheck.allowed) {
      this.rateLimited++
      return {
        allowed: false,
        reason: `Rate limit exceeded for IP ${ip}. Max ${this.config.rateLimitPerMinute} requests/minute.`,
        code: 'RATE_LIMITED_IP',
        retryAfterMs: ipCheck.retryAfterMs,
      }
    }

    // Also rate limit per user (if authenticated)
    if (userId !== 'anonymous') {
      const userKey = `user:${userId}`
      const userCheck = this.rateLimiter.check(userKey)
      if (!userCheck.allowed) {
        this.rateLimited++
        return {
          allowed: false,
          reason: `Rate limit exceeded for user ${userId}. Max ${this.config.rateLimitPerMinute} requests/minute.`,
          code: 'RATE_LIMITED_USER',
          retryAfterMs: userCheck.retryAfterMs,
        }
      }
    }

    // 4. Concurrency check
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
    } else if (this.concurrencyLimiter.getActive() > this.config.maxConcurrentRequests * 0.7) {
      pressure = 'low'
    }

    return { allowed: true, pressure }
  }

  /**
   * Release a concurrency slot after the request completes.
   */
  release() {
    this.concurrencyLimiter.release()
  }

  /**
   * Record a successful operation (closes circuit breaker).
   */
  recordSuccess(operationKey: string) {
    this.circuitBreaker.recordSuccess(operationKey)
  }

  /**
   * Record a failed operation (may open circuit breaker).
   */
  recordFailure(operationKey: string) {
    this.circuitBreaker.recordFailure(operationKey)
  }

  /**
   * Get current governor metrics for monitoring.
   */
  getMetrics(): GovernorMetrics {
    const memStatus = this.memoryMonitor.getStatus()
    return {
      totalRequests: this.totalRequests,
      rateLimited: this.rateLimited,
      activeRequests: this.concurrencyLimiter.getActive(),
      maxActiveRequests: this.concurrencyLimiter.getMaxObserved(),
      queuedRequests: 0, // We reject instead of queue
      memoryUsageMB: memStatus.usageMB,
      memoryPercent: memStatus.percent,
      memoryStatus: memStatus.status,
      circuitsOpen: this.circuitBreaker.getOpenCircuitCount(),
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
   * Destroy the governor and clean up intervals.
   */
  destroy() {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval)
      this.cleanupInterval = null
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
}

export const governor = process.env.NODE_ENV === 'production'
  ? (globalForGovernor.governor ?? new ResourceGovernor(devGovernorConfig))
  : new ResourceGovernor(devGovernorConfig)

if (process.env.NODE_ENV === 'production') globalForGovernor.governor = governor
