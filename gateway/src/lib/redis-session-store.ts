/**
 * Phase 3.3: Redis Session Store for Gateway
 *
 * Stores session metadata in Redis HASH keys with TTL-based expiry.
 * Falls back to an in-memory Map when Redis is unavailable,
 * ensuring graceful degradation.
 *
 * Key layout:
 *   zenic:gw:session:{id}  →  HASH with session metadata fields
 *
 * Usage:
 *   const store = new RedisSessionStore({ redisUrl: 'redis://localhost:6379' })
 *   await store.connect()
 *   await store.set('sess-123', { userId: 'u1', state: 'active' }, 1800_000)
 *   const data = await store.get('sess-123')
 */

import Redis from 'ioredis'

// ── Types ──────────────────────────────────────────────────────

export interface SessionData {
  [key: string]: string | number | boolean | null
}

export interface RedisSessionStoreConfig {
  redisUrl?: string
  keyPrefix?: string
  defaultTtlMs?: number
  connectTimeoutMs?: number
}

export interface SessionStoreStats {
  backend: 'redis' | 'memory'
  redisUrl: string
  keyPrefix: string
  defaultTtlMs: number
  memoryStoreCount: number
  connected: boolean
}

// ── Implementation ─────────────────────────────────────────────

export class RedisSessionStore {
  private redis: Redis | null = null
  private redisAvailable = false
  private readonly redisUrl: string
  private readonly keyPrefix: string
  private readonly defaultTtlMs: number
  private readonly connectTimeoutMs: number

  // In-memory fallback
  private memoryStore = new Map<string, { data: SessionData; expiresAt: number }>()

  constructor(config: RedisSessionStoreConfig = {}) {
    this.redisUrl = config.redisUrl ?? process.env.REDIS_URL ?? 'redis://localhost:6379'
    this.keyPrefix = config.keyPrefix ?? 'zenic:gw:session'
    this.defaultTtlMs = config.defaultTtlMs ?? 1_800_000 // 30 minutes
    this.connectTimeoutMs = config.connectTimeoutMs ?? 5_000
  }

  // ── Connection Management ──────────────────────────────────

  /**
   * Connect to Redis. Returns true if connected, false if falling back to memory.
   */
  async connect(): Promise<boolean> {
    try {
      this.redis = new Redis(this.redisUrl, {
        connectTimeout: this.connectTimeoutMs,
        commandTimeout: 5_000,
        retryStrategy: (times) => {
          // Stop retrying after 10 attempts
          if (times > 10) {
            console.warn('[RedisSessionStore] Max retries reached — giving up on Redis')
            return null
          }
          // Exponential backoff: 100ms, 200ms, 400ms, etc.
          return Math.min(times * 100, 3_000)
        },
        lazyConnect: true,
        maxRetriesPerRequest: 2,
      })

      // Attempt connection
      await this.redis.connect()
      await this.redis.ping()

      this.redisAvailable = true
      console.log(`[RedisSessionStore] Connected to ${this.redisUrl}`)

      // Handle disconnection gracefully
      this.redis.on('error', (err) => {
        if (this.redisAvailable) {
          console.warn(`[RedisSessionStore] Redis error: ${err.message}`)
          this.redisAvailable = false
        }
      })

      this.redis.on('ready', () => {
        if (!this.redisAvailable) {
          console.log('[RedisSessionStore] Redis reconnected')
          this.redisAvailable = true
        }
      })

      return true
    } catch (err) {
      console.warn(
        `[RedisSessionStore] Redis connection failed — using in-memory fallback:`,
        err instanceof Error ? err.message : err,
      )
      this.redisAvailable = false
      this.redis = null
      return false
    }
  }

  /**
   * Disconnect from Redis gracefully.
   */
  async disconnect(): Promise<void> {
    if (this.redis) {
      try {
        await this.redis.quit()
      } catch {
        // Ignore — we're shutting down
      }
      this.redis = null
      this.redisAvailable = false
    }
  }

  /**
   * Check if Redis is available.
   */
  isAvailable(): boolean {
    return this.redisAvailable && this.redis !== null
  }

  /**
   * Ping Redis to check connectivity.
   */
  async ping(): Promise<boolean> {
    if (!this.redis) return false
    try {
      const result = await this.redis.ping()
      this.redisAvailable = result === 'PONG'
      return this.redisAvailable
    } catch {
      this.redisAvailable = false
      return false
    }
  }

  // ── Core Operations ────────────────────────────────────────

  /**
   * Store session metadata with a TTL.
   *
   * @param id - Session identifier
   * @param data - Session metadata to store
   * @param ttlMs - Time-to-live in milliseconds (uses default if not provided)
   */
  async set(id: string, data: SessionData, ttlMs?: number): Promise<void> {
    const ttl = ttlMs ?? this.defaultTtlMs
    const key = `${this.keyPrefix}:${id}`

    // Always store in-memory fallback
    this.memoryStore.set(id, {
      data,
      expiresAt: Date.now() + ttl,
    })

    // Store in Redis if available
    if (this.redisAvailable && this.redis) {
      try {
        // Flatten data to string values for Redis HASH
        const mapping: Record<string, string> = {}
        for (const [field, value] of Object.entries(data)) {
          mapping[field] = value === null ? '' : String(value)
        }

        await this.redis.hset(key, mapping)
        await this.redis.pexpire(key, ttl) // TTL in milliseconds
      } catch (err) {
        console.warn(
          `[RedisSessionStore] Redis SET failed for session ${id}:`,
          err instanceof Error ? err.message : err,
        )
        this.redisAvailable = false
      }
    }
  }

  /**
   * Retrieve session metadata by ID.
   *
   * Tries Redis first; falls back to in-memory if Redis fails.
   *
   * @param id - Session identifier
   * @returns Session data, or null if not found / expired
   */
  async get(id: string): Promise<SessionData | null> {
    // Try Redis first
    if (this.redisAvailable && this.redis) {
      try {
        const key = `${this.keyPrefix}:${id}`
        const data = await this.redis.hgetall(key)

        if (data && Object.keys(data).length > 0) {
          // Refresh TTL on access (extend session on read)
          const ttl = this.defaultTtlMs
          await this.redis.pexpire(key, ttl)

          // Sync to in-memory
          this.memoryStore.set(id, {
            data,
            expiresAt: Date.now() + ttl,
          })

          return data
        }
      } catch (err) {
        console.warn(
          `[RedisSessionStore] Redis GET failed for session ${id}:`,
          err instanceof Error ? err.message : err,
        )
        this.redisAvailable = false
      }
    }

    // Fall back to in-memory
    const entry = this.memoryStore.get(id)
    if (!entry) return null

    // Check expiry
    if (Date.now() > entry.expiresAt) {
      this.memoryStore.delete(id)
      return null
    }

    return entry.data
  }

  /**
   * Delete a session by ID from both Redis and in-memory.
   *
   * @param id - Session identifier
   * @returns True if the session existed in either store
   */
  async delete(id: string): Promise<boolean> {
    let found = false

    // Delete from in-memory
    if (this.memoryStore.delete(id)) {
      found = true
    }

    // Delete from Redis
    if (this.redisAvailable && this.redis) {
      try {
        const key = `${this.keyPrefix}:${id}`
        const deleted = await this.redis.del(key)
        if (deleted > 0) found = true
      } catch (err) {
        console.warn(
          `[RedisSessionStore] Redis DELETE failed for session ${id}:`,
          err instanceof Error ? err.message : err,
        )
        this.redisAvailable = false
      }
    }

    return found
  }

  // ── Maintenance ────────────────────────────────────────────

  /**
   * Clean up expired sessions from the in-memory fallback.
   * Redis handles its own expiry via TTL.
   *
   * @returns Number of expired sessions cleaned up
   */
  cleanupExpired(): number {
    let cleaned = 0
    const now = Date.now()

    for (const [id, entry] of this.memoryStore) {
      if (now > entry.expiresAt) {
        this.memoryStore.delete(id)
        cleaned++
      }
    }

    return cleaned
  }

  /**
   * Get store statistics.
   */
  getStats(): SessionStoreStats {
    return {
      backend: this.redisAvailable ? 'redis' : 'memory',
      redisUrl: this.redisAvailable ? this.redisUrl : 'unavailable',
      keyPrefix: this.keyPrefix,
      defaultTtlMs: this.defaultTtlMs,
      memoryStoreCount: this.memoryStore.size,
      connected: this.redisAvailable,
    }
  }
}

// ── Singleton ──────────────────────────────────────────────────

const globalForSessionStore = globalThis as unknown as {
  redisSessionStore: RedisSessionStore | undefined
}

export function getRedisSessionStore(): RedisSessionStore | undefined {
  return globalForSessionStore.redisSessionStore
}

export function setRedisSessionStore(store: RedisSessionStore): void {
  globalForSessionStore.redisSessionStore = store
}

/**
 * Create and connect a RedisSessionStore if CACHE_PROVIDER=redis.
 * Returns undefined if Redis is not configured.
 */
export async function initRedisSessionStore(): Promise<RedisSessionStore | undefined> {
  const cacheProvider = process.env.CACHE_PROVIDER
  if (cacheProvider !== 'redis') {
    return undefined
  }

  const store = new RedisSessionStore({
    redisUrl: process.env.REDIS_URL,
    keyPrefix: process.env.REDIS_KEY_PREFIX
      ? `${process.env.REDIS_KEY_PREFIX}:gw:session`
      : 'zenic:gw:session',
  })

  await store.connect()
  setRedisSessionStore(store)
  return store
}
