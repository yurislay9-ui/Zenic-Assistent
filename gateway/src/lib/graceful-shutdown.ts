/**
 * #58 Fix: Graceful Shutdown with SQLite Protection (FASE 1.5)
 * 
 * Prevents OOM kills from corrupting SQLite databases and the Merkle chain.
 * 
 * Problem:
 * When Kubernetes/Docker sends SIGTERM, the process has a limited grace period
 * before SIGKILL. If we don't flush SQLite's WAL and close connections properly,
 * the database can be left in an inconsistent state — especially the Merkle
 * audit chain which requires sequential, unbroken entries.
 * 
 * Shutdown sequence:
 * 1. Stop accepting new requests (signal health=shutting_down)
 * 2. Wait for in-flight requests to complete (max 30s)
 * 3. Flush WriteQueue completely
 * 4. Destroy DurableWriteLog (close Redis connection cleanly)
 * 5. Run WAL checkpoint TRUNCATE on all SQLite databases
 * 6. Close all Prisma connections
 * 7. Exit cleanly
 */

import type { ResourceGovernor } from '@/lib/resource-governor'
import type { WriteQueue } from '@/lib/write-queue'
import type { DurableWriteLog } from '@/lib/durable-write-log'

/**
 * Minimal DB interface — we only need $queryRaw and $disconnect.
 * This avoids importing PrismaClient directly (which triggers client generation).
 */
interface DbLike {
  $queryRaw: (query: TemplateStringsArray) => Promise<unknown>
  $disconnect: () => Promise<void>
}

export class GracefulShutdown {
  private shuttingDown = false
  private activeRequests = 0
  private governor: ResourceGovernor
  private writeQueue: WriteQueue
  private db: DbLike
  private durableLog: DurableWriteLog | null
  private startTime = Date.now()

  constructor(deps: {
    governor: ResourceGovernor
    writeQueue: WriteQueue
    db: DbLike
    durableLog?: DurableWriteLog
  }) {
    this.governor = deps.governor
    this.writeQueue = deps.writeQueue
    this.db = deps.db
    this.durableLog = deps.durableLog ?? null
  }

  /**
   * Signal handler for SIGTERM, SIGINT.
   * Safe to call multiple times — only executes the shutdown sequence once.
   */
  async handleSignal(signal: string): Promise<void> {
    // Guard against multiple invocations
    if (this.shuttingDown) {
      console.warn(`[Shutdown] Already shutting down. Ignoring ${signal}.`)
      return
    }

    this.shuttingDown = true
    console.warn(`[Shutdown] Graceful shutdown initiated by ${signal}`)

    // Step 1: Wait for in-flight requests to complete (max 30s)
    const drainStart = Date.now()
    const maxDrainMs = 30000

    while (this.activeRequests > 0) {
      const elapsed = Date.now() - drainStart
      if (elapsed >= maxDrainMs) {
        console.warn(
          `[Shutdown] Drain timeout (${maxDrainMs}ms). ${this.activeRequests} requests still active. Proceeding with shutdown.`
        )
        break
      }

      console.warn(
        `[Shutdown] Waiting for ${this.activeRequests} active requests to complete... (${Math.round(elapsed / 1000)}s/${Math.round(maxDrainMs / 1000)}s)`
      )

      // Wait 1 second before checking again
      await new Promise(resolve => setTimeout(resolve, 1000))
    }

    if (this.activeRequests === 0) {
      console.warn('[Shutdown] All in-flight requests completed.')
    }

    // Step 2: Flush WriteQueue completely
    try {
      console.warn('[Shutdown] Flushing write queue...')
      await this.writeQueue.destroy()
      console.warn('[Shutdown] Write queue flushed successfully.')
    } catch (error) {
      console.warn('[Shutdown] Write queue flush failed (non-fatal):', error)
    }

    // Step 2.5: Destroy DurableWriteLog (close Redis cleanly)
    // After the WriteQueue is flushed, all WAL entries should be acknowledged.
    // Close the Redis connection to release resources.
    if (this.durableLog) {
      try {
        console.warn('[Shutdown] Closing DurableWriteLog Redis connection...')
        await this.durableLog.destroy()
        console.warn('[Shutdown] DurableWriteLog destroyed.')
      } catch (error) {
        console.warn('[Shutdown] DurableWriteLog destroy failed (non-fatal):', error)
      }
    }

    // Step 3: Run WAL checkpoint TRUNCATE
    try {
      console.warn('[Shutdown] Running WAL checkpoint TRUNCATE...')
      await this.db.$queryRaw`PRAGMA wal_checkpoint(TRUNCATE)`
      console.warn('[Shutdown] WAL checkpoint TRUNCATE completed.')
    } catch (error) {
      console.warn('[Shutdown] WAL checkpoint failed (non-fatal):', error)
    }

    // Step 4: Close all Prisma connections
    try {
      console.warn('[Shutdown] Disconnecting from database...')
      await this.db.$disconnect()
      console.warn('[Shutdown] Database disconnected.')
    } catch (error) {
      console.warn('[Shutdown] Database disconnect failed (non-fatal):', error)
    }

    // Step 5: Clean up governor resources
    try {
      this.governor.destroy()
    } catch {
      // Ignore — we're shutting down anyway
    }

    // Step 6: Exit cleanly
    console.warn('[Shutdown] Graceful shutdown complete.')
    process.exit(0)
  }

  /**
   * Check if the server is shutting down.
   * Used by the health endpoint and request middleware.
   */
  isShuttingDown(): boolean {
    return this.shuttingDown
  }

  /**
   * Track the start of an active request.
   * Call at the beginning of each request handler.
   */
  requestStart(): void {
    this.activeRequests++
  }

  /**
   * Track the end of an active request.
   * Call when a request handler completes (in finally block).
   */
  requestEnd(): void {
    if (this.activeRequests > 0) {
      this.activeRequests--
    }
  }

  /**
   * Health check endpoint data.
   * Returns the current shutdown status for orchestrators.
   */
  getHealthStatus(): {
    status: 'healthy' | 'shutting_down'
    activeRequests: number
    uptime: number
  } {
    return {
      status: this.shuttingDown ? 'shutting_down' : 'healthy',
      activeRequests: this.activeRequests,
      uptime: Date.now() - this.startTime,
    }
  }
}

// ===== Singleton =====
// The GracefulShutdown instance is created during instrumentation
// and stored globally for access from route handlers and middleware.

const globalForShutdown = globalThis as unknown as {
  gracefulShutdown: GracefulShutdown | undefined
}

export function getGracefulShutdown(): GracefulShutdown | undefined {
  return globalForShutdown.gracefulShutdown
}

export function setGracefulShutdown(shutdown: GracefulShutdown): void {
  globalForShutdown.gracefulShutdown = shutdown
}
