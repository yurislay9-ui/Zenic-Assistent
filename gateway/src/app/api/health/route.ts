import { NextResponse } from 'next/server';
import { governor } from '@/lib/resource-governor';
import { writeQueue } from '@/lib/write-queue';
import { getAllCacheStats } from '@/lib/cache';
import { getScanCacheStats } from '@/lib/scan-cache';

/**
 * GET /api/health
 * 
 * #58 Fix: Health endpoint with system pressure metrics.
 * #57 Fix: Cache metrics for monitoring hit rates.
 * #59 Fix: Scan cache metrics for incremental scanning stats.
 * Public endpoint — no auth required.
 * 
 * Returns:
 * - Overall health status (ok / degraded / critical)
 * - Memory pressure metrics
 * - Rate limiting stats
 * - Concurrency stats
 * - Circuit breaker status
 * - Write queue stats
 * - SQLite info
 * - Cache stats (feature gates, server state, general)
 * - Scan cache stats
 */
export async function GET() {
  const metrics = governor.getMetrics();
  const queueStats = writeQueue.getStats();
  const memStatus = metrics.memoryStatus;
  const cacheStats = getAllCacheStats();
  const scanStats = getScanCacheStats();

  // Determine overall health
  let status: 'ok' | 'degraded' | 'critical' = 'ok'
  let message = 'All systems operational'

  if (memStatus === 'critical' || metrics.circuitsOpen >= 3) {
    status = 'critical'
    message = 'System under heavy pressure — some operations may be rejected'
  } else if (memStatus === 'warning' || metrics.circuitsOpen >= 1 || metrics.activeRequests > 30) {
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

    // Write queue stats
    writeQueue: queueStats,

    // DB status
    database: dbInfo,

    // #57 Fix: Cache metrics
    cache: cacheStats,

    // #59 Fix: Scan cache metrics
    scanCache: scanStats,
  }, {
    status: status === 'critical' ? 503 : 200,
    headers: {
      'Cache-Control': 'no-store',
      'X-Health-Status': status,
      'X-Memory-Percent': metrics.memoryPercent.toString(),
    },
  });
}
