/**
 * #57 Fix: Cache Abstraction Layer — Horizontal Scalability
 * 
 * Previous state:
 * - Feature gates: DB query on every request (no cache)
 * - Server state: In-memory Map<> (not shared between instances)
 * - No TTL, no eviction, no cache invalidation
 * 
 * This module provides:
 * 1. ICache interface — swap between MemoryCache and RedisCache in production
 * 2. MemoryCache — LRU + TTL cache for single-instance (sandbox)
 * 3. RedisCache — full ioredis implementation for multi-instance (production)
 * 4. Cache-aside pattern — read from cache, on miss read from DB, write to cache
 * 5. Feature gate cache — avoids DB lookup on every request
 * 
 * Production migration: Set CACHE_PROVIDER=redis + CACHE_URL=redis://...
 * Everything else is transparent — same ICache interface.
 */

// ===== TYPES =====

export interface CacheEntry<T> {
  value: T
  expiresAt: number  // epoch ms, 0 = never expires
  createdAt: number
  accessCount: number
  lastAccessedAt: number
}

export interface CacheStats {
  size: number
  maxSize: number
  hits: number
  misses: number
  hitRate: number
  evictions: number
  expiredPurges: number
}

export interface ICache<T = unknown> {
  get(key: string): Promise<T | null>
  set(key: string, value: T, ttlMs?: number): Promise<void>
  delete(key: string): Promise<boolean>
  has(key: string): Promise<boolean>
  clear(): Promise<void>
  getStats(): CacheStats
  getSize(): number
}

// ===== MEMORY CACHE (LRU + TTL) =====

class LRUNode<T> {
  key: string
  entry: CacheEntry<T>
  prev: LRUNode<T> | null = null
  next: LRUNode<T> | null = null

  constructor(key: string, entry: CacheEntry<T>) {
    this.key = key
    this.entry = entry
  }
}

export class MemoryCache<T = unknown> implements ICache<T> {
  private map = new Map<string, LRUNode<T>>()
  private head: LRUNode<T> | null = null  // Most recently used
  private tail: LRUNode<T> | null = null  // Least recently used
  private maxSize: number
  private defaultTtlMs: number
  private stats = {
    hits: 0,
    misses: 0,
    evictions: 0,
    expiredPurges: 0,
  }
  private purgeInterval: ReturnType<typeof setInterval> | null = null

  constructor(options: { maxSize?: number; defaultTtlMs?: number } = {}) {
    this.maxSize = options.maxSize ?? 500
    this.defaultTtlMs = options.defaultTtlMs ?? 60_000 // 1 minute default

    // Periodic purge of expired entries (every 30s)
    this.purgeInterval = setInterval(() => this.purgeExpired(), 30_000)
  }

  async get(key: string): Promise<T | null> {
    const node = this.map.get(key)
    if (!node) {
      this.stats.misses++
      return null
    }

    const now = Date.now()

    // Check TTL expiration
    if (node.entry.expiresAt > 0 && now > node.entry.expiresAt) {
      this.removeNode(node)
      this.map.delete(key)
      this.stats.misses++
      this.stats.expiredPurges++
      return null
    }

    // Update access stats
    node.entry.accessCount++
    node.entry.lastAccessedAt = now

    // Move to head (most recently used)
    this.moveToHead(node)

    this.stats.hits++
    return node.entry.value
  }

  async set(key: string, value: T, ttlMs?: number): Promise<void> {
    const now = Date.now()
    const effectiveTtl = ttlMs ?? this.defaultTtlMs

    const entry: CacheEntry<T> = {
      value,
      expiresAt: effectiveTtl > 0 ? now + effectiveTtl : 0, // 0 = never expires
      createdAt: now,
      accessCount: 0,
      lastAccessedAt: now,
    }

    // If key exists, update it
    const existing = this.map.get(key)
    if (existing) {
      existing.entry = entry
      this.moveToHead(existing)
      return
    }

    // Create new node
    const node = new LRUNode(key, entry)
    this.map.set(key, node)
    this.addToHead(node)

    // Evict LRU if over capacity
    while (this.map.size > this.maxSize) {
      const lru = this.tail
      if (lru) {
        this.removeNode(lru)
        this.map.delete(lru.key)
        this.stats.evictions++
      } else {
        break
      }
    }
  }

  async delete(key: string): Promise<boolean> {
    const node = this.map.get(key)
    if (!node) return false
    this.removeNode(node)
    this.map.delete(key)
    return true
  }

  async has(key: string): Promise<boolean> {
    const node = this.map.get(key)
    if (!node) return false
    // Check expiration
    if (node.entry.expiresAt > 0 && Date.now() > node.entry.expiresAt) {
      this.removeNode(node)
      this.map.delete(key)
      return false
    }
    return true
  }

  async clear(): Promise<void> {
    this.map.clear()
    this.head = null
    this.tail = null
  }

  getStats(): CacheStats {
    const total = this.stats.hits + this.stats.misses
    return {
      size: this.map.size,
      maxSize: this.maxSize,
      hits: this.stats.hits,
      misses: this.stats.misses,
      hitRate: total > 0 ? Math.round((this.stats.hits / total) * 10000) / 100 : 0,
      evictions: this.stats.evictions,
      expiredPurges: this.stats.expiredPurges,
    }
  }

  getSize(): number {
    return this.map.size
  }

  /**
   * Purge all expired entries. Called periodically and on demand.
   */
  purgeExpired(): number {
    const now = Date.now()
    let purged = 0

    for (const [key, node] of this.map) {
      if (node.entry.expiresAt > 0 && now > node.entry.expiresAt) {
        this.removeNode(node)
        this.map.delete(key)
        purged++
      }
    }

    this.stats.expiredPurges += purged
    return purged
  }

  /**
   * Destroy the cache and clean up intervals.
   */
  destroy() {
    if (this.purgeInterval) {
      clearInterval(this.purgeInterval)
      this.purgeInterval = null
    }
    this.map.clear()
    this.head = null
    this.tail = null
  }

  // ===== LRU Doubly-Linked List Operations =====

  private addToHead(node: LRUNode<T>) {
    node.prev = null
    node.next = this.head

    if (this.head) {
      this.head.prev = node
    }
    this.head = node

    if (!this.tail) {
      this.tail = node
    }
  }

  private removeNode(node: LRUNode<T>) {
    if (node.prev) {
      node.prev.next = node.next
    } else {
      this.head = node.next
    }

    if (node.next) {
      node.next.prev = node.prev
    } else {
      this.tail = node.prev
    }

    node.prev = null
    node.next = null
  }

  private moveToHead(node: LRUNode<T>) {
    this.removeNode(node)
    this.addToHead(node)
  }
}

// ===== REDIS CACHE (Production — ioredis) =====

/**
 * RedisCache — full implementation using ioredis.
 *
 * When deploying with multiple instances, set:
 *   CACHE_PROVIDER=redis
 *   CACHE_URL=redis://localhost:6379
 *
 * The factory function createCache() will automatically
 * return a RedisCache instead of MemoryCache.
 *
 * Features:
 * - Key prefixing (default "zenic:") to namespace cache entries
 * - JSON serialization/deserialization with error handling
 * - TTL via Redis PX (millisecond) option
 * - Local hit/miss/eviction stats counters
 * - Graceful degradation: never throws on Redis errors
 * - Built-in reconnection with ioredis retry strategy
 * - SCAN-based clear() (only clears prefixed keys, never FLUSHDB)
 * - Health check: ping(), isConnected(), destroy()
 */

/** Lazy-loaded ioredis constructor type */
type RedisConstructor = new (options: import('ioredis').RedisOptions) => import('ioredis').Redis

/** Attempt to dynamically import ioredis — returns null if not available */
async function loadIoredis(): Promise<RedisConstructor | null> {
  try {
    const mod = await import('ioredis')
    return (mod.default ?? mod) as RedisConstructor
  } catch {
    return null
  }
}

export class RedisCache<T = unknown> implements ICache<T> {
  private client: import('ioredis').Redis | null = null
  private prefix: string
  private defaultTtlMs: number
  private _connected = false
  private initPromise: Promise<void> | null = null
  private stats = {
    hits: 0,
    misses: 0,
    evictions: 0,
    expiredPurges: 0, // Not tracked in Redis (TTL handles expiry)
  }

  constructor(options: { url?: string; prefix?: string; defaultTtlMs?: number } = {}) {
    this.prefix = options.prefix ?? 'zenic:'
    this.defaultTtlMs = options.defaultTtlMs ?? 60_000

    const url = options.url || process.env.CACHE_URL || 'redis://localhost:6379'

    // Kick off async init — methods will await it as needed
    this.initPromise = this.initialize(url)
  }

  /**
   * Initialize the Redis client. If ioredis is not installed or the
   * connection fails, we degrade gracefully — all methods become no-ops.
   */
  private async initialize(url: string): Promise<void> {
    const Redis = await loadIoredis()
    if (!Redis) {
      console.warn('[Cache:Redis] ioredis package not found. RedisCache will operate in degraded mode (all ops are no-op).')
      return
    }

    try {
      this.client = new Redis({
        url,
        // Built-in retry strategy: reconnect with exponential backoff
        retryStrategy(times: number) {
          if (times > 20) {
            // Give up after 20 retries
            console.warn('[Cache:Redis] Max reconnection attempts reached. Giving up.')
            return null // Stop retrying
          }
          const delay = Math.min(times * 200, 5000) // 200ms, 400ms, ... up to 5s
          return delay
        },
        maxRetriesPerRequest: 3, // Per-command timeout retries
        enableReadyCheck: true,
        lazyConnect: false,
      })

      this.client.on('ready', () => {
        this._connected = true
      })

      this.client.on('error', (err: Error) => {
        // Don't throw — just log. ioredis will retry automatically.
        console.error('[Cache:Redis] Connection error:', err.message)
        this._connected = false
      })

      this.client.on('close', () => {
        this._connected = false
      })

      this.client.on('reconnecting', () => {
        console.info('[Cache:Redis] Reconnecting...')
      })

      // Wait for the client to be ready (or timeout)
      await this.client?.ping().catch(() => {
        // Connection failed initially — ioredis will keep retrying
        console.warn('[Cache:Redis] Initial connection failed. ioredis will retry automatically.')
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      console.error('[Cache:Redis] Failed to initialize ioredis client:', message)
      this.client = null
    }
  }

  /** Ensure initialization is complete before any operation */
  private async ensureReady(): Promise<boolean> {
    if (this.initPromise) {
      await this.initPromise
      this.initPromise = null
    }
    return this.client !== null && this._connected
  }

  /** Build the full Redis key with prefix */
  private fullKey(key: string): string {
    return `${this.prefix}${key}`
  }

  /**
   * Serialize a value to a Redis string.
   * Handles primitives and objects. Returns null on serialization error.
   */
  private serialize(value: T): string | null {
    try {
      return JSON.stringify(value)
    } catch (err) {
      console.error('[Cache:Redis] Serialization error:', err)
      return null
    }
  }

  /**
   * Deserialize a Redis string back to type T.
   * Returns null on deserialization error.
   */
  private deserialize(raw: string | null): T | null {
    if (raw === null || raw === undefined) return null
    try {
      return JSON.parse(raw) as T
    } catch (err) {
      console.error('[Cache:Redis] Deserialization error:', err)
      return null
    }
  }

  // ===== ICache interface =====

  async get(key: string): Promise<T | null> {
    const ready = await this.ensureReady()
    if (!ready || !this.client) {
      this.stats.misses++
      return null
    }

    try {
      const raw = await this.client.get(this.fullKey(key))
      if (raw === null || raw === undefined) {
        this.stats.misses++
        return null
      }

      const value = this.deserialize(raw)
      if (value === null) {
        this.stats.misses++
        return null
      }

      this.stats.hits++
      return value
    } catch (err) {
      console.error('[Cache:Redis] get error:', err instanceof Error ? err.message : err)
      this.stats.misses++
      return null
    }
  }

  async set(key: string, value: T, ttlMs?: number): Promise<void> {
    const ready = await this.ensureReady()
    if (!ready || !this.client) return

    const effectiveTtl = ttlMs ?? this.defaultTtlMs
    const serialized = this.serialize(value)
    if (serialized === null) return // Serialization failed

    try {
      if (effectiveTtl > 0) {
        await this.client.set(this.fullKey(key), serialized, 'PX', effectiveTtl)
      } else {
        // No TTL — persist indefinitely
        await this.client.set(this.fullKey(key), serialized)
      }
    } catch (err) {
      console.error('[Cache:Redis] set error:', err instanceof Error ? err.message : err)
    }
  }

  async delete(key: string): Promise<boolean> {
    const ready = await this.ensureReady()
    if (!ready || !this.client) return false

    try {
      const result = await this.client.del(this.fullKey(key))
      if (result > 0) {
        this.stats.evictions++
        return true
      }
      return false
    } catch (err) {
      console.error('[Cache:Redis] delete error:', err instanceof Error ? err.message : err)
      return false
    }
  }

  async has(key: string): Promise<boolean> {
    const ready = await this.ensureReady()
    if (!ready || !this.client) return false

    try {
      const result = await this.client.exists(this.fullKey(key))
      return result > 0
    } catch (err) {
      console.error('[Cache:Redis] has error:', err instanceof Error ? err.message : err)
      return false
    }
  }

  /**
   * Clear all keys with the configured prefix.
   * Uses SCAN (not FLUSHDB) to avoid destroying other data in the Redis instance.
   */
  async clear(): Promise<void> {
    const ready = await this.ensureReady()
    if (!ready || !this.client) return

    try {
      let cursor = '0'
      do {
        const [nextCursor, keys] = await this.client.scan(
          cursor,
          'MATCH',
          `${this.prefix}*`,
          'COUNT',
          100
        )
        cursor = nextCursor

        if (keys.length > 0) {
          // Use a pipeline for batch deletion
          const pipeline = this.client.pipeline()
          for (const key of keys) {
            pipeline.del(key)
          }
          await pipeline.exec()
          this.stats.evictions += keys.length
        }
      } while (cursor !== '0')
    } catch (err) {
      console.error('[Cache:Redis] clear error:', err instanceof Error ? err.message : err)
    }
  }

  getStats(): CacheStats {
    const total = this.stats.hits + this.stats.misses
    return {
      size: -1, // Redis doesn't expose a cheap size count for prefixed keys
      maxSize: -1,
      hits: this.stats.hits,
      misses: this.stats.misses,
      hitRate: total > 0 ? Math.round((this.stats.hits / total) * 10000) / 100 : 0,
      evictions: this.stats.evictions,
      expiredPurges: this.stats.expiredPurges,
    }
  }

  /**
   * Synchronous size approximation.
   * Redis doesn't provide a cheap way to count prefixed keys,
   * so this returns -1 to indicate "not available".
   * Use getApproximateSize() for an async accurate count.
   */
  getSize(): number {
    return -1
  }

  /**
   * Get approximate size by counting keys with the prefix via SCAN.
   * This is relatively expensive — avoid calling in hot paths.
   */
  async getApproximateSize(): Promise<number> {
    const ready = await this.ensureReady()
    if (!ready || !this.client) return 0

    try {
      let count = 0
      let cursor = '0'
      do {
        const [nextCursor, keys] = await this.client.scan(
          cursor,
          'MATCH',
          `${this.prefix}*`,
          'COUNT',
          100
        )
        cursor = nextCursor
        count += keys.length
      } while (cursor !== '0')
      return count
    } catch (err) {
      console.error('[Cache:Redis] getApproximateSize error:', err instanceof Error ? err.message : err)
      return 0
    }
  }

  // ===== Extended methods (beyond ICache) =====

  /**
   * Close the Redis connection and clean up.
   * Call this when shutting down the process.
   */
  async destroy(): Promise<void> {
    try {
      if (this.client) {
        this.client.removeAllListeners()
        await this.client.quit()
        this.client = null
        this._connected = false
      }
    } catch (err) {
      // quit() can throw if already closed — that's fine
      console.warn('[Cache:Redis] destroy error (may already be closed):', err instanceof Error ? err.message : err)
      this.client = null
      this._connected = false
    }
  }

  /**
   * Ping the Redis server. Returns true if the server responds, false otherwise.
   */
  async ping(): Promise<boolean> {
    const ready = await this.ensureReady()
    if (!ready || !this.client) return false

    try {
      const result = await this.client.ping()
      return result === 'PONG'
    } catch {
      return false
    }
  }

  /**
   * Check if the Redis client is currently connected and ready.
   */
  isConnected(): boolean {
    return this._connected && this.client !== null
  }
}

// ===== CACHE FACTORY =====

/**
 * Create the appropriate cache based on environment configuration.
 * - CACHE_PROVIDER=redis → RedisCache (requires ioredis)
 * - default → MemoryCache (LRU + TTL, single instance)
 *
 * If redis is requested but ioredis is not available, falls back to MemoryCache
 * and logs a warning.
 */
export function createCache<T = unknown>(options?: {
  maxSize?: number
  defaultTtlMs?: number
  redisUrl?: string
  prefix?: string
}): ICache<T> {
  const provider = process.env.CACHE_PROVIDER || 'memory'

  if (provider === 'redis') {
    try {
      // Attempt to require ioredis synchronously to decide which cache to use.
      // RedisCache itself does async init — this just checks if the package exists.
      require.resolve('ioredis')
      return new RedisCache<T>({
        url: options?.redisUrl || process.env.CACHE_URL,
        prefix: options?.prefix,
        defaultTtlMs: options?.defaultTtlMs,
      })
    } catch {
      console.warn('[Cache] CACHE_PROVIDER=redis but ioredis is not installed. Falling back to MemoryCache.')
      return new MemoryCache<T>({
        maxSize: options?.maxSize,
        defaultTtlMs: options?.defaultTtlMs,
      })
    }
  }

  return new MemoryCache<T>({
    maxSize: options?.maxSize,
    defaultTtlMs: options?.defaultTtlMs,
  })
}

// ===== SINGLETON CACHES =====

const globalForCache = globalThis as unknown as {
  featureGateCache: ICache<FeatureGateCacheEntry> | undefined
  serverStateCache: ICache<ServerStateCacheEntry> | undefined
  generalCache: ICache | undefined
}

/**
 * Feature gate cache — avoids DB lookup on every request.
 * TTL: 30 seconds (feature gates rarely change during a session).
 * Max size: 100 (we have ~10 gates, 100 is generous).
 */
export interface FeatureGateCacheEntry {
  key: string
  name: string
  enabled: boolean
  minRole: string
  requireApproval: boolean
}

export const featureGateCache: ICache<FeatureGateCacheEntry> =
  globalForCache.featureGateCache ??
  createCache<FeatureGateCacheEntry>({ maxSize: 100, defaultTtlMs: 30_000, prefix: 'zenic:fg:' })

if (process.env.NODE_ENV !== 'production') globalForCache.featureGateCache = featureGateCache

/**
 * Server state cache — avoids DB lookup on every list/status request.
 * TTL: 10 seconds (server status changes on start/stop).
 * Max size: 50 (we have 9 servers, 50 is generous).
 */
export interface ServerStateCacheEntry {
  serverId: string
  name: string
  status: string
  startedAt: number | null
  error: string | null
  toolsCount: number
  resourcesCount: number
  pid: number | null
}

export const serverStateCache: ICache<ServerStateCacheEntry> =
  globalForCache.serverStateCache ??
  createCache<ServerStateCacheEntry>({ maxSize: 50, defaultTtlMs: 10_000, prefix: 'zenic:ss:' })

if (process.env.NODE_ENV !== 'production') globalForCache.serverStateCache = serverStateCache

/**
 * General-purpose cache for arbitrary data.
 * TTL: 60 seconds, max 500 entries.
 */
export const generalCache: ICache =
  globalForCache.generalCache ??
  createCache({ maxSize: 500, defaultTtlMs: 60_000, prefix: 'zenic:gen:' })

if (process.env.NODE_ENV !== 'production') globalForCache.generalCache = generalCache

// ===== CACHE-ASIDE HELPERS =====

/**
 * Cache-aside read: try cache first, on miss read from source and cache the result.
 * This is the standard pattern for DB-backed caches.
 */
export async function cacheAside<T>(
  cache: ICache<T>,
  key: string,
  source: () => Promise<T>,
  ttlMs?: number
): Promise<T> {
  const cached = await cache.get(key)
  if (cached !== null) {
    return cached
  }

  const value = await source()
  if (value !== null && value !== undefined) {
    await cache.set(key, value, ttlMs)
  }

  return value
}

/**
 * Invalidate a cache entry — call after DB writes that change the cached data.
 */
export async function cacheInvalidate<T>(
  cache: ICache<T>,
  key: string
): Promise<boolean> {
  return cache.delete(key)
}

/**
 * Get aggregate stats from all singleton caches.
 */
export function getAllCacheStats(): Record<string, CacheStats> {
  return {
    featureGates: featureGateCache.getStats(),
    serverState: serverStateCache.getStats(),
    general: generalCache.getStats(),
  }
}
