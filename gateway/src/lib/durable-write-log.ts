/**
 * Phase 3.1: Durable Write-Ahead Log (WAL) — Redis-backed persistence
 *
 * Problem:
 * The WriteQueue batches DB writes in memory. On process crash (kill -9),
 * all queued writes are LOST. The GracefulShutdown tries to flush, but
 * hard kills bypass it entirely.
 *
 * Solution:
 * Before executing any write operation, serialize its metadata to Redis.
 * After successful execution, remove it (acknowledge). On startup, recover
 * any pending writes and re-enqueue them through registered replay handlers.
 *
 * Redis structure:
 * - LIST  `zenic:wal:pending`       — ordered queue of entry IDs
 * - HASH  `zenic:wal:entry:{id}`    — individual entry data:
 *     { id, category, payload (JSON), enqueuedAt, retryCount }
 *
 * Best-effort:
 * If Redis is unavailable, the WAL degrades gracefully — all methods
 * become no-ops and the WriteQueue operates in legacy in-memory mode.
 * Never throws from WAL operations.
 */

// ===== TYPES =====

export interface WALEntry {
  id: string
  category: string
  payload: unknown
  enqueuedAt: number
  retryCount: number
}

export type ReplayHandler = (payload: unknown) => Promise<void>

interface WALEntryData {
  id: string
  category: string
  payload: string          // JSON-serialized
  enqueuedAt: string       // stored as string in Redis HASH
  retryCount: string       // stored as string in Redis HASH
}

// ===== LAZY IOREDIS LOADING (same pattern as RedisCache) =====

type RedisConstructor = new (options: import('ioredis').RedisOptions) => import('ioredis').Redis

async function loadIoredis(): Promise<RedisConstructor | null> {
  try {
    const mod = await import('ioredis')
    return (mod.default ?? mod) as RedisConstructor
  } catch {
    return null
  }
}

// ===== DURABLE WRITE-AHEAD LOG =====

export class DurableWriteLog {
  private client: import('ioredis').Redis | null = null
  private _connected = false
  private initPromise: Promise<void> | null = null
  private replayHandlers = new Map<string, ReplayHandler>()
  private readonly PENDING_KEY = 'zenic:wal:pending'
  private readonly ENTRY_PREFIX = 'zenic:wal:entry:'

  constructor(options: { url?: string } = {}) {
    const url = options.url || process.env.REDIS_URL || 'redis://localhost:6379'
    this.initPromise = this.initialize(url)
  }

  // ===== INITIALIZATION =====

  /**
   * Initialize the Redis client. If ioredis is not installed or the
   * connection fails, we degrade gracefully — all methods become no-ops.
   */
  private async initialize(url: string): Promise<void> {
    const Redis = await loadIoredis()
    if (!Redis) {
      console.warn('[WAL] ioredis package not found. DurableWriteLog will operate in degraded mode (all ops are no-op).')
      return
    }

    try {
      this.client = new Redis({
        url,
        retryStrategy(times: number) {
          if (times > 20) {
            console.warn('[WAL] Max reconnection attempts reached. Giving up.')
            return null
          }
          const delay = Math.min(times * 200, 5000)
          return delay
        },
        maxRetriesPerRequest: 3,
        enableReadyCheck: true,
        lazyConnect: false,
      })

      this.client.on('ready', () => {
        this._connected = true
      })

      this.client.on('error', (err: Error) => {
        console.error('[WAL] Connection error:', err.message)
        this._connected = false
      })

      this.client.on('close', () => {
        this._connected = false
      })

      this.client.on('reconnecting', () => {
        console.warn('[WAL] Reconnecting...')
      })

      await this.client?.ping().catch(() => {
        console.warn('[WAL] Initial connection failed. ioredis will retry automatically.')
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      console.error('[WAL] Failed to initialize ioredis client:', message)
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

  /** Check if WAL is connected and operational */
  isConnected(): boolean {
    return this._connected && this.client !== null
  }

  // ===== CORE API =====

  /**
   * Append a pending write to the WAL.
   * Stores the entry data in a Redis HASH and pushes the ID to the pending list.
   * Returns the entry ID, or empty string if Redis is unavailable.
   */
  async append(category: string, payload: unknown): Promise<string> {
    try {
      const ready = await this.ensureReady()
      if (!ready || !this.client) return ''

      const id = crypto.randomUUID()
      const now = Date.now()

      const entryData: Record<string, string> = {
        id,
        category,
        payload: JSON.stringify(payload),
        enqueuedAt: String(now),
        retryCount: '0',
      }

      // Use a pipeline for atomicity: add entry HASH + push ID to pending LIST
      const pipeline = this.client.pipeline()
      pipeline.hset(`${this.ENTRY_PREFIX}${id}`, entryData)
      pipeline.rpush(this.PENDING_KEY, id)
      await pipeline.exec()

      return id
    } catch (err) {
      console.error('[WAL] append error:', err instanceof Error ? err.message : err)
      return ''
    }
  }

  /**
   * Acknowledge (complete) a write — remove it from the WAL.
   * Deletes the entry HASH and removes the ID from the pending list.
   */
  async acknowledge(entryId: string): Promise<void> {
    try {
      const ready = await this.ensureReady()
      if (!ready || !this.client || !entryId) return

      // Use a pipeline: remove from pending list + delete entry hash
      const pipeline = this.client.pipeline()
      pipeline.lrem(this.PENDING_KEY, 0, entryId)
      pipeline.del(`${this.ENTRY_PREFIX}${entryId}`)
      await pipeline.exec()
    } catch (err) {
      console.error('[WAL] acknowledge error:', err instanceof Error ? err.message : err)
    }
  }

  /**
   * Recover all pending entries from the WAL.
   * Called on startup to re-enqueue writes that were not completed
   * before the previous process crashed.
   *
   * Returns an array of pending entries with deserialized payloads.
   */
  async recover(): Promise<Array<{ id: string; category: string; payload: unknown }>> {
    try {
      const ready = await this.ensureReady()
      if (!ready || !this.client) return []

      // Get all entry IDs from the pending list
      const entryIds = await this.client.lrange(this.PENDING_KEY, 0, -1)
      if (entryIds.length === 0) return []

      // Fetch all entry data in a pipeline
      const pipeline = this.client.pipeline()
      for (const id of entryIds) {
        pipeline.hgetall(`${this.ENTRY_PREFIX}${id}`)
      }
      const results = await pipeline.exec()

      if (!results) return []

      const entries: Array<{ id: string; category: string; payload: unknown }> = []

      for (let i = 0; i < results.length; i++) {
        const [err, data] = results[i]
        if (err || !data) {
          // Entry data missing — clean up stale ID from the pending list
          console.warn(`[WAL] recover: entry ${entryIds[i]} data missing, removing from pending list`)
          try {
            await this.client.lrem(this.PENDING_KEY, 0, entryIds[i])
          } catch {
            // Ignore — best effort
          }
          continue
        }

        const entryData = data as unknown as WALEntryData
        if (!entryData.id || !entryData.category) {
          console.warn(`[WAL] recover: entry ${entryIds[i]} has missing fields, skipping`)
          continue
        }

        let payload: unknown = null
        try {
          payload = JSON.parse(entryData.payload)
        } catch {
          console.warn(`[WAL] recover: entry ${entryIds[i]} payload parse error, using raw string`)
          payload = entryData.payload
        }

        entries.push({
          id: entryData.id,
          category: entryData.category,
          payload,
        })
      }

      if (entries.length > 0) {
        console.warn(`[WAL] recover: found ${entries.length} pending writes from previous session`)
      }

      return entries
    } catch (err) {
      console.error('[WAL] recover error:', err instanceof Error ? err.message : err)
      return []
    }
  }

  /**
   * Register a replay handler for a given category.
   * When entries are recovered, the WriteQueue uses these handlers
   * to reconstruct the actual DB write operations from the stored payload.
   */
  registerReplayHandler(category: string, handler: ReplayHandler): void {
    this.replayHandlers.set(category, handler)
  }

  /**
   * Get the replay handler for a given category.
   * Used by WriteQueue to reconstruct operations during recovery.
   */
  getReplayHandler(category: string): ReplayHandler | undefined {
    return this.replayHandlers.get(category)
  }

  /**
   * Get the number of pending entries in the WAL.
   * Returns 0 if Redis is unavailable.
   */
  async getPendingCount(): Promise<number> {
    try {
      const ready = await this.ensureReady()
      if (!ready || !this.client) return 0

      return await this.client.llen(this.PENDING_KEY)
    } catch (err) {
      console.error('[WAL] getPendingCount error:', err instanceof Error ? err.message : err)
      return 0
    }
  }

  /**
   * Increment the retry count for a pending entry.
   * Called when a recovered write fails and needs to be re-enqueued.
   */
  async incrementRetryCount(entryId: string): Promise<void> {
    try {
      const ready = await this.ensureReady()
      if (!ready || !this.client || !entryId) return

      const key = `${this.ENTRY_PREFIX}${entryId}`
      await this.client.hincrby(key, 'retryCount', 1)
    } catch (err) {
      console.error('[WAL] incrementRetryCount error:', err instanceof Error ? err.message : err)
    }
  }

  /**
   * Close the Redis connection cleanly.
   * Called during graceful shutdown after the WriteQueue is flushed.
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
      console.warn('[WAL] destroy error (may already be closed):', err instanceof Error ? err.message : err)
      this.client = null
      this._connected = false
    }
  }
}
