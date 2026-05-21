import { NextResponse } from 'next/server';
import { governor } from '@/lib/resource-governor';
import { writeQueue } from '@/lib/write-queue';
import { getAllCacheStats } from '@/lib/cache';
import { getScanCacheStats } from '@/lib/scan-cache';
import { getGracefulShutdown } from '@/lib/graceful-shutdown';
import { getRedisSessionStore } from '@/lib/redis-session-store';
import { vectorStore } from '@/lib/vector-store';

/**
 * GET /api/health
 * 
 * #58 Fix: Health endpoint with system pressure metrics.
 * #57 Fix: Cache metrics for monitoring hit rates.
 * #59 Fix: Scan cache metrics for incremental scanning stats.
 * FASE 1.4: DB health metrics (write queue depth, write latency).
 * FASE 1.5: Graceful shutdown status for orchestrators.
 * Phase 3.4: Redis, PostgreSQL, circuit breaker, WAL, and session store stats.
 * 
 * Public endpoint — no auth required.
 * 
 * Returns:
 * - Overall health status (ok / degraded / critical / shutting_down)
 * - Memory pressure metrics
 * - Rate limiting stats
 * - Concurrency stats
 * - Circuit breaker status (with detailed stats)
 * - DB health stats (FASE 1.4)
 * - Write queue stats
 * - SQLite info
 * - Cache stats (feature gates, server state, general)
 * - Scan cache stats
 * - Shutdown status (FASE 1.5)
 * - Redis connectivity (Phase 3.4)
 * - WAL pending count (Phase 3.4)
 * - Session store stats — Redis vs memory (Phase 3.4)
 * - Vector store stats — pgvector vs memory (Phase 4.1)
 */
export async function GET() {
  const metrics = governor.getMetrics();
  const queueStats = writeQueue.getStats();
  const memStatus = metrics.memoryStatus;
  const cacheStats = getAllCacheStats();
  const scanStats = getScanCacheStats();
  const shutdown = getGracefulShutdown();
  const shutdownStatus = shutdown?.getHealthStatus();

  // FASE 1.5: Check if we're shutting down
  const isShuttingDown = shutdownStatus?.status === 'shutting_down'

  // Determine overall health
  let status: 'ok' | 'degraded' | 'critical' | 'shutting_down' = 'ok'
  let message = 'All systems operational'

  if (isShuttingDown) {
    status = 'shutting_down'
    message = 'Server is shutting down — no new requests accepted'
  } else if (memStatus === 'critical' || metrics.circuitsOpen >= 3 || metrics.dbStatus === 'critical') {
    status = 'critical'
    message = 'System under heavy pressure — some operations may be rejected'
  } else if (memStatus === 'warning' || metrics.circuitsOpen >= 1 || metrics.activeRequests > 30 || metrics.dbStatus === 'degraded') {
    status = 'degraded'
    message = 'System under moderate pressure — performance may be reduced'
  }

  // Get DB size info
  let dbInfo = { configured: false, connected: false }
  try {
    const { db } = await import('@/lib/db')
    await db.$queryRaw`SELECT 1`
    dbInfo = { configured: true, connected: true }
  } catch {
    dbInfo = { configured: true, connected: false }
  }

  // Phase 3.4: Redis connectivity check
  let redisInfo: {
    available: boolean;
    sessionStoreBackend: 'redis' | 'memory' | 'none';
    sessionStoreCount: number;
  } = {
    available: false,
    sessionStoreBackend: 'none',
    sessionStoreCount: 0,
  }

  if (process.env.CACHE_PROVIDER === 'redis') {
    try {
      const sessionStore = getRedisSessionStore()
      if (sessionStore) {
        const stats = sessionStore.getStats()
        redisInfo = {
          available: stats.connected,
          sessionStoreBackend: stats.backend,
          sessionStoreCount: stats.memoryStoreCount,
        }
      } else {
        // Try a direct Redis ping
        try {
          const Redis = (await import('ioredis')).default
          const client = new Redis(process.env.REDIS_URL ?? 'redis://localhost:6379', {
            connectTimeout: 3000,
            lazyConnect: true,
            maxRetriesPerRequest: 1,
          })
          await client.connect()
          await client.ping()
          redisInfo.available = true
          await client.quit()
        } catch {
          redisInfo.available = false
        }
        redisInfo.sessionStoreBackend = 'none'
        redisInfo.sessionStoreCount = 0
      }
    } catch {
      redisInfo.available = false
    }
  }

  // Phase 3.4: Circuit breaker detailed stats from the governor
  const circuitBreakerStats = {
    circuitsOpen: metrics.circuitsOpen,
    rateLimiterBackend: metrics.rateLimiterBackend,
  }

  // Phase 3.4: WAL (Write-Ahead Log) pending count
  let walInfo: { pendingCount: number; mode: string } = { pendingCount: 0, mode: 'unknown' }
  try {
    const { db } = await import('@/lib/db')
    // Get WAL mode status
    const journalModeResult = await db.$queryRaw`PRAGMA journal_mode` as Array<{ journal_mode: string }>
    walInfo.mode = journalModeResult?.[0]?.journal_mode ?? 'unknown'

    // Get WAL checkpoint info to estimate pending writes
    // wal_checkpoint returns: busy, log, checkpoint
    const checkpointResult = await db.$queryRaw`PRAGMA wal_checkpoint(PASSIVE)` as Array<{ busy: number; log: number; checkpoint: number }>
    if (checkpointResult && checkpointResult[0]) {
      // pending = log frames - checkpointed frames
      walInfo.pendingCount = (checkpointResult[0].log ?? 0) - (checkpointResult[0].checkpoint ?? 0)
    }
  } catch {
    // Non-critical — WAL info is optional
  }

  // Phase 3.4: Session store stats
  const sessionStoreInfo = (() => {
    const sessionStore = getRedisSessionStore()
    if (sessionStore) {
      return sessionStore.getStats()
    }
    return {
      backend: 'none' as const,
      redisUrl: 'not configured',
      keyPrefix: 'n/a',
      defaultTtlMs: 0,
      memoryStoreCount: 0,
      connected: false,
    }
  })()

  return NextResponse.json({
    status,
    message,
    timestamp: new Date().toISOString(),
    uptime: Math.round(process.uptime()),
    
    // #56 Fix: Memory metrics
    memory: {
      heapUsedMB: metrics.memoryUsageMB,
      heapPercent: metrics.memoryPercent,
      status: metrics.memoryStatus,
      rssMB: Math.round(process.memoryUsage().rss / 1024 / 1024),
      externalMB: Math.round(process.memoryUsage().external / 1024 / 1024),
    },

    // #58 Fix: Governor metrics
    governor: {
      totalRequests: metrics.totalRequests,
      rateLimited: metrics.rateLimited,
      rateLimitPercent: metrics.totalRequests > 0 
        ? Math.round((metrics.rateLimited / metrics.totalRequests) * 100 * 100) / 100 
        : 0,
      activeRequests: metrics.activeRequests,
      maxActiveRequests: metrics.maxActiveRequests,
      maxConcurrent: governor.getConfig().maxConcurrentRequests,
      circuitsOpen: metrics.circuitsOpen,
      config: {
        rateLimitPerMinute: governor.getConfig().rateLimitPerMinute,
        maxConcurrentRequests: governor.getConfig().maxConcurrentRequests,
        memoryCriticalPercent: governor.getConfig().memoryCriticalPercent,
      },
    },

    // FASE 1.4: DB health metrics
    dbHealth: {
      status: metrics.dbStatus,
      writeQueueLength: metrics.writeQueueLength,
      writeLatencyMs: metrics.writeLatencyMs,
    },

    // Write queue stats
    writeQueue: queueStats,

    // DB status
    database: dbInfo,

    // #57 Fix: Cache metrics
    cache: cacheStats,

    // #59 Fix: Scan cache metrics
    scanCache: scanStats,

    // FASE 1.5: Shutdown status for Kubernetes/Docker orchestrators
    shutdown: shutdownStatus ?? { status: 'healthy' as const, activeRequests: 0, uptime: 0 },

    // Phase 3.4: Redis connectivity and session store info
    redis: redisInfo,

    // Phase 3.4: Circuit breaker detailed stats
    circuitBreakers: circuitBreakerStats,

    // Phase 3.4: WAL (Write-Ahead Log) pending count
    wal: walInfo,

    // Phase 3.4: Session store stats (Redis vs memory)
    sessionStore: sessionStoreInfo,

    // Phase 4.1: Vector store stats (pgvector vs memory)
    vectorStore: vectorStore.healthCheck(),
  }, {
    status: (status === 'critical' || status === 'shutting_down') ? 503 : 200,
    headers: {
      'Cache-Control': 'no-store',
      'X-Health-Status': status,
      'X-Memory-Percent': metrics.memoryPercent.toString(),
    },
  });
}
