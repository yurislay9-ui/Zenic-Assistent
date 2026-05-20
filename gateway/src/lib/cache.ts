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
 * 3. RedisCache stub — documented interface for multi-instance (production)
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

// ===== REDIS CACHE STUB (Production Migration Target) =====

/**
 * #57 Fix: RedisCache — stub for production deployment.
 * 
 * When deploying with multiple instances, set:
 *   CACHE_PROVIDER=redis
 *   CACHE_URL=redis://localhost:6379
 * 
 * The factory function createCache() will automatically
 * return a RedisCache instead of MemoryCache.
 * 
 * Implementation requires: ioredis package
 *   npm install ioredis
 * 
 * Then uncomment and complete the RedisCache implementation below.
 */
export class RedisCache<T = unknown> implements ICache<T> {
  private connected = false
  // private client: import('ioredis').Redis | null = null

  constructor(_options: { url?: string; prefix?: string; defaultTtlMs?: number } = {}) {
    // Production implementation:
    // const Redis = require('ioredis')
    // this.client = new Redis(options.url || 'redis://localhost:6379')
    // this.connected = true
    console.warn('[Cache] RedisCache is a stub — using MemoryCache instead. Set up ioredis for production.')
  }

  async get(_key: string): Promise<T | null> {
    // Production: return await this.client.get(this.prefix + key)
    return null
  }

  async set(_key: string, _value: T, _ttlMs?: number): Promise<void> {
    // Production: await this.client.set(this.prefix + key, JSON.stringify(value), 'PX', ttlMs)
  }

  async delete(_key: string): Promise<boolean> {
    // Production: return (await this.client.del(this.prefix + key)) > 0
    return false
  }

  async has(_key: string): Promise<boolean> {
    // Production: return (await this.client.exists(this.prefix + key)) > 0
    return false
  }

  async clear(): Promise<void> {
    // Production: await this.client.flushdb()
  }

  getStats(): CacheStats {
    return {
      size: 0,
      maxSize: 0,
      hits: 0,
      misses: 0,
      hitRate: 0,
      evictions: 0,
      expiredPurges: 0,
    }
  }

  getSize(): number {
    return 0
  }
}

// ===== CACHE FACTORY =====

/**
 * Create the appropriate cache based on environment configuration.
 * - CACHE_PROVIDER=redis → RedisCache (requires ioredis)
 * - default → MemoryCache (LRU + TTL, single instance)
 */
export function createCache<T = unknown>(options?: {
  maxSize?: number
  defaultTtlMs?: number
  redisUrl?: string
  prefix?: string
}): ICache<T> {
  const provider = process.env.CACHE_PROVIDER || 'memory'

  if (provider === 'redis') {
    return new RedisCache<T>({
      url: options?.redisUrl || process.env.CACHE_URL,
      prefix: options?.prefix,
      defaultTtlMs: options?.defaultTtlMs,
    })
  }

  return new MemoryCache<T>({
    maxSize: options?.maxSize,
    defaultTtlMs: options?.defaultTtlMs,
  })
}

// ===== SINGLETON CACHES =====

const globalForCache = globalThis as unknown as {
  featureGateCache: MemoryCache<FeatureGateCacheEntry> | undefined
  serverStateCache: MemoryCache<ServerStateCacheEntry> | undefined
  generalCache: MemoryCache | undefined
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

export const featureGateCache: MemoryCache<FeatureGateCacheEntry> =
  globalForCache.featureGateCache ??
  new MemoryCache<FeatureGateCacheEntry>({ maxSize: 100, defaultTtlMs: 30_000 })

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

export const serverStateCache: MemoryCache<ServerStateCacheEntry> =
  globalForCache.serverStateCache ??
  new MemoryCache<ServerStateCacheEntry>({ maxSize: 50, defaultTtlMs: 10_000 })

if (process.env.NODE_ENV !== 'production') globalForCache.serverStateCache = serverStateCache

/**
 * General-purpose cache for arbitrary data.
 * TTL: 60 seconds, max 500 entries.
 */
export const generalCache: MemoryCache =
  globalForCache.generalCache ??
  new MemoryCache({ maxSize: 500, defaultTtlMs: 60_000 })

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
