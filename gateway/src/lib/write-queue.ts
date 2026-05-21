/**
 * #58 Fix: Write Queue — Batch non-urgent DB writes
 * 
 * Instead of every audit/action logging writing to DB immediately,
 * queue them and flush in batches. This:
 * 1. Reduces SQLITE_BUSY contention (fewer individual writes)
 * 2. Improves response latency (writes don't block the response)
 * 3. Allows automatic retry with the db.ts withRetry utility
 * 
 * FASE 1.4: Now reports metrics to ResourceGovernor after each flush,
 * so the governor can reject requests when DB is under pressure.
 * 
 * Phase 3.1: Durable Write-Ahead Log (WAL) integration.
 * When a DurableWriteLog is provided, every enqueued write is first
 * persisted to Redis before execution. After successful execution,
 * it is acknowledged (removed) from Redis. On startup, any pending
 * writes are recovered and re-enqueued via registered replay handlers.
 * If no DurableWriteLog is provided, the queue operates in legacy
 * in-memory mode (backward compatible).
 * 
 * Usage:
 *   writeQueue.enqueue('audit', () => db.approvalAction.create({ data: ... }))
 *   writeQueue.enqueue('metric', () => db.metric.create({ data: ... }))
 */

import { governor } from '@/lib/resource-governor'
import { DurableWriteLog, type ReplayHandler } from '@/lib/durable-write-log'

interface QueueEntry {
  category: string
  operation: () => Promise<unknown>
  enqueuedAt: number
  retryCount: number
  /** Phase 3.1: WAL entry ID — links this in-memory entry to its Redis record */
  walId?: string
}

export class WriteQueue {
  private queue: QueueEntry[] = []
  private flushing = false
  private maxBatchSize: number
  private flushIntervalMs: number
  private maxRetries: number
  private intervalHandle: ReturnType<typeof setInterval> | null = null
  private stats = {
    enqueued: 0,
    flushed: 0,
    failed: 0,
    lastFlushAt: 0,
  }
  // FASE 1.4: Track write latency for DB health monitoring
  private totalWriteLatencyMs = 0
  private writeCount = 0
  // Phase 3.1: Optional durable WAL for crash resilience
  private durableLog: DurableWriteLog | null

  constructor(options: {
    maxBatchSize?: number
    flushIntervalMs?: number
    maxRetries?: number
    durableLog?: DurableWriteLog
  } = {}) {
    this.maxBatchSize = options.maxBatchSize ?? 20
    this.flushIntervalMs = options.flushIntervalMs ?? 5000 // 5 seconds
    this.maxRetries = options.maxRetries ?? 2
    this.durableLog = options.durableLog ?? null

    // Auto-flush periodically
    this.intervalHandle = setInterval(() => {
      this.flush().catch(() => {})
    }, this.flushIntervalMs)

    // Ensure queue is flushed on process exit
    process.on('beforeExit', () => this.flush())
  }

  /**
   * Enqueue a write operation for later batch execution.
   * Returns immediately — the operation will execute within the next flush cycle.
   * 
   * Phase 3.1: If a DurableWriteLog is configured, the write metadata
   * is also persisted to Redis (best-effort, non-blocking). The returned
   * walId links the in-memory entry to its Redis record.
   */
  enqueue(category: string, operation: () => Promise<unknown>, payload?: unknown): void {
    const entry: QueueEntry = {
      category,
      operation,
      enqueuedAt: Date.now(),
      retryCount: 0,
    }

    // Phase 3.1: Persist to WAL before adding to memory queue
    if (this.durableLog) {
      // Fire-and-forget WAL append — never block enqueue
      this.durableLog.append(category, payload ?? { category }).then((walId) => {
        entry.walId = walId
      }).catch(() => {
        // WAL failure must never block the queue
      })
    }

    this.queue.push(entry)
    this.stats.enqueued++

    // Flush immediately if batch is full
    if (this.queue.length >= this.maxBatchSize) {
      this.flush().catch(() => {})
    }
  }

  /**
   * Flush all queued operations in a batch.
   * Uses the batchWrite utility from db.ts for transaction support.
   * 
   * FASE 1.4: After each flush, reports metrics (queue length + write latency)
   * to the ResourceGovernor so it can detect DB pressure.
   */
  async flush(): Promise<{ flushed: number; failed: number }> {
    if (this.flushing || this.queue.length === 0) {
      // Even on empty flush, report current queue length to governor
      this.reportMetrics(0)
      return { flushed: 0, failed: 0 }
    }

    this.flushing = true
    const batch = this.queue.splice(0, this.maxBatchSize)
    let flushed = 0
    let failed = 0
    let batchLatencySum = 0

    // Execute each operation individually (not in a transaction)
    // because they may be independent and we don't want one failure
    // to roll back the entire batch
    for (const entry of batch) {
      try {
        await entry.operation()
        flushed++
        // FASE 1.4: Track latency from enqueue to successful execution
        const writeLatency = Date.now() - entry.enqueuedAt
        batchLatencySum += writeLatency
        this.totalWriteLatencyMs += writeLatency
        this.writeCount++

        // Phase 3.1: Acknowledge (remove) from WAL after successful execution
        if (this.durableLog && entry.walId) {
          this.durableLog.acknowledge(entry.walId).catch(() => {
            // WAL acknowledge failure must never block the flush loop
          })
        }
      } catch (error) {
        entry.retryCount++

        if (entry.retryCount <= this.maxRetries) {
          // Re-enqueue for retry
          this.queue.push(entry)
        } else {
          failed++
          console.warn(
            `[WriteQueue] Failed after ${entry.retryCount} retries: ${entry.category}`,
            error
          )
        }
      }
    }

    this.stats.flushed += flushed
    this.stats.failed += failed
    this.stats.lastFlushAt = Date.now()
    this.flushing = false

    // FASE 1.4: Report metrics to governor after each flush
    // Average latency across the batch (or 0 if nothing was flushed)
    const avgLatency = flushed > 0 ? Math.round(batchLatencySum / flushed) : 0
    this.reportMetrics(avgLatency)

    return { flushed, failed }
  }

  /**
   * FASE 1.4: Report write metrics to the ResourceGovernor.
   * This is non-blocking and will not throw — governor metric updates
   * must never block the flush loop.
   */
  private reportMetrics(writeLatencyMs: number): void {
    try {
      governor.updateDbMetrics({
        writeQueueLength: this.queue.length,
        writeLatencyMs,
      })
    } catch {
      // Governor metric reporting must never block the flush loop
      // Silently ignore errors (governor might not be initialized yet)
    }
  }

  /**
   * Get the current queue length.
   */
  get length(): number {
    return this.queue.length
  }

  /**
   * Phase 3.1: Recover pending writes from the WAL and re-enqueue them.
   * Called on startup. For each recovered entry, looks up the registered
   * replay handler for its category and reconstructs the DB write operation.
   * Entries without a registered replay handler are logged as warnings.
   */
  async recoverFromWal(): Promise<number> {
    if (!this.durableLog) return 0

    try {
      const pending = await this.durableLog.recover()
      if (pending.length === 0) return 0

      let recovered = 0
      for (const entry of pending) {
        const handler = this.durableLog.getReplayHandler(entry.category)
        if (!handler) {
          console.warn(
            `[WriteQueue] recoverFromWal: no replay handler for category "${entry.category}" (entry ${entry.id}). Skipping.`
          )
          continue
        }

        // Create a QueueEntry that uses the replay handler as its operation
        this.queue.push({
          category: entry.category,
          operation: () => handler(entry.payload),
          enqueuedAt: entry.enqueuedAt ?? Date.now(),
          retryCount: 0, // Reset retry count on recovery
          walId: entry.id,
        })
        recovered++
      }

      if (recovered > 0) {
        console.warn(`[WriteQueue] recoverFromWal: re-enqueued ${recovered} pending writes from WAL`)
      }

      return recovered
    } catch (err) {
      console.error('[WriteQueue] recoverFromWal error:', err instanceof Error ? err.message : err)
      return 0
    }
  }

  /**
   * Phase 3.1: Register a replay handler for a given category.
   * Passthrough to the DurableWriteLog's registerReplayHandler.
   * If no DurableWriteLog is configured, this is a no-op.
   */
  registerReplayHandler(category: string, handler: ReplayHandler): void {
    if (this.durableLog) {
      this.durableLog.registerReplayHandler(category, handler)
    }
  }

  /**
   * Phase 3.1: Get the DurableWriteLog instance (if any).
   * Used by GracefulShutdown to destroy the WAL connection.
   */
  getDurableLog(): DurableWriteLog | null {
    return this.durableLog
  }

  /**
   * Get queue statistics.
   */
  getStats() {
    return {
      ...this.stats,
      queueLength: this.queue.length,
      categories: this.getCategoryBreakdown(),
      avgWriteLatencyMs: this.writeCount > 0
        ? Math.round(this.totalWriteLatencyMs / this.writeCount)
        : 0,
      walEnabled: this.durableLog !== null && this.durableLog.isConnected(),
    }
  }

  private getCategoryBreakdown(): Record<string, number> {
    const breakdown: Record<string, number> = {}
    for (const entry of this.queue) {
      breakdown[entry.category] = (breakdown[entry.category] || 0) + 1
    }
    return breakdown
  }

  /**
   * Destroy the queue and clean up.
   * FASE 1.5: Called by GracefulShutdown to flush remaining writes.
   */
  async destroy() {
    if (this.intervalHandle) {
      clearInterval(this.intervalHandle)
      this.intervalHandle = null
    }
    await this.flush()
  }
}

// ===== Singleton =====

const globalForQueue = globalThis as unknown as {
  writeQueue: WriteQueue | undefined
  durableWriteLog: DurableWriteLog | undefined
}

/**
 * Create a DurableWriteLog instance if REDIS_URL is set.
 * This provides crash resilience for the WriteQueue — pending writes
 * survive process kills because they're persisted to Redis.
 */
const durableWriteLog =
  globalForQueue.durableWriteLog ??
  (process.env.REDIS_URL ? new DurableWriteLog({ url: process.env.REDIS_URL }) : undefined)

if (process.env.NODE_ENV !== 'production' && durableWriteLog) {
  globalForQueue.durableWriteLog = durableWriteLog
}

export const writeQueue =
  globalForQueue.writeQueue ??
  new WriteQueue({
    maxBatchSize: 20,
    flushIntervalMs: 5000,
    maxRetries: 2,
    durableLog: durableWriteLog,
  })

if (process.env.NODE_ENV !== 'production') globalForQueue.writeQueue = writeQueue

/**
 * On startup, recover any pending writes from the WAL.
 * This runs asynchronously — recovered writes will be re-enqueued
 * and executed on the next flush cycle.
 */
if (durableWriteLog) {
  writeQueue.recoverFromWal().catch((err) => {
    console.error('[WriteQueue] WAL recovery failed on startup:', err instanceof Error ? err.message : err)
  })
}
