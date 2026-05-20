/**
 * #58 Fix: Write Queue — Batch non-urgent DB writes
 * 
 * Instead of every audit/action logging writing to DB immediately,
 * queue them and flush in batches. This:
 * 1. Reduces SQLITE_BUSY contention (fewer individual writes)
 * 2. Improves response latency (writes don't block the response)
 * 3. Allows automatic retry with the db.ts withRetry utility
 * 
 * Usage:
 *   writeQueue.enqueue('audit', () => db.approvalAction.create({ data: ... }))
 *   writeQueue.enqueue('metric', () => db.metric.create({ data: ... }))
 */

interface QueueEntry {
  category: string
  operation: () => Promise<unknown>
  enqueuedAt: number
  retryCount: number
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

  constructor(options: {
    maxBatchSize?: number
    flushIntervalMs?: number
    maxRetries?: number
  } = {}) {
    this.maxBatchSize = options.maxBatchSize ?? 20
    this.flushIntervalMs = options.flushIntervalMs ?? 5000 // 5 seconds
    this.maxRetries = options.maxRetries ?? 2

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
   */
  enqueue(category: string, operation: () => Promise<unknown>): void {
    this.queue.push({
      category,
      operation,
      enqueuedAt: Date.now(),
      retryCount: 0,
    })
    this.stats.enqueued++

    // Flush immediately if batch is full
    if (this.queue.length >= this.maxBatchSize) {
      this.flush().catch(() => {})
    }
  }

  /**
   * Flush all queued operations in a batch.
   * Uses the batchWrite utility from db.ts for transaction support.
   */
  async flush(): Promise<{ flushed: number; failed: number }> {
    if (this.flushing || this.queue.length === 0) {
      return { flushed: 0, failed: 0 }
    }

    this.flushing = true
    const batch = this.queue.splice(0, this.maxBatchSize)

    let flushed = 0
    let failed = 0

    // Execute each operation individually (not in a transaction)
    // because they may be independent and we don't want one failure
    // to roll back the entire batch
    for (const entry of batch) {
      try {
        await entry.operation()
        flushed++
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

    return { flushed, failed }
  }

  /**
   * Get the current queue length.
   */
  get length(): number {
    return this.queue.length
  }

  /**
   * Get queue statistics.
   */
  getStats() {
    return {
      ...this.stats,
      queueLength: this.queue.length,
      categories: this.getCategoryBreakdown(),
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
}

export const writeQueue =
  globalForQueue.writeQueue ??
  new WriteQueue({
    maxBatchSize: 20,
    flushIntervalMs: 5000,
    maxRetries: 2,
  })

if (process.env.NODE_ENV !== 'production') globalForQueue.writeQueue = writeQueue
