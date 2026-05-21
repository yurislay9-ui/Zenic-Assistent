/**
 * ZENIC-AGENTS v16 - Performance Dashboard (Phase 4.4)
 *
 * Real-time performance monitoring dashboard data aggregator.
 * Collects metrics from all subsystems and provides a unified
 * API for the performance dashboard UI.
 *
 * Metrics collected:
 * - ResourceGovernor: rate limiting, concurrency, memory, circuit breakers
 * - WriteQueue: write throughput, latency, queue depth
 * - VectorStore: search latency, embedding count, backend status
 * - HealthAggregator: liveness/readiness check results
 * - System: CPU, memory, event loop lag, GC stats
 *
 * Usage:
 *   const dashboard = getPerformanceDashboard()
 *   const snapshot = dashboard.getSnapshot()
 *   // Returns comprehensive metrics for dashboard rendering
 */

import { governor } from '@/lib/resource-governor';
import { vectorStore } from '@/lib/vector-store';

// ===== TYPES =====

export interface DashboardSnapshot {
  timestamp: number;
  uptime: number;
  system: SystemMetrics;
  governor: GovernorDashboardMetrics;
  writeQueue: WriteQueueMetrics;
  vectorStore: VectorDashboardMetrics;
  health: HealthDashboardMetrics;
  timeSeries: TimeSeriesBucket;
}

export interface SystemMetrics {
  memoryUsageMB: number;
  memoryTotalMB: number;
  memoryPercent: number;
  cpuUsagePercent: number;
  eventLoopLagMs: number;
  gcCount: number;
  gcTotalMs: number;
  activeHandles: number;
  activeRequests: number;
}

export interface GovernorDashboardMetrics {
  totalRequests: number;
  rateLimited: number;
  rateLimitPercent: number;
  activeRequests: number;
  maxConcurrentRequests: number;
  concurrentUtilization: number;
  memoryStatus: 'normal' | 'warning' | 'critical';
  dbStatus: 'healthy' | 'degraded' | 'critical';
  circuitsOpen: number;
  rateLimiterBackend: 'memory' | 'redis';
  circuitBreakerBackend: 'memory' | 'redis';
  writeQueueLength: number;
  writeLatencyMs: number;
}

export interface WriteQueueMetrics {
  queueLength: number;
  totalEnqueued: number;
  totalFlushed: number;
  totalFailed: number;
  avgWriteLatencyMs: number;
  walEnabled: boolean;
  categories: Record<string, number>;
}

export interface VectorDashboardMetrics {
  backend: 'pgvector' | 'memory' | 'none';
  totalEmbeddings: number;
  dimensions: number;
  avgSearchLatencyMs: number;
  totalSearches: number;
  totalInserts: number;
  hnswM: number;
  hnswEfConstruction: number;
}

export interface HealthDashboardMetrics {
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
  checks: Record<string, {
    status: string;
    message: string;
    latencyMs: number;
  }>;
  lastCheckedAt: number;
}

export interface TimeSeriesBucket {
  requestsPerSecond: number;
  avgLatencyMs: number;
  errorRate: number;
  p50LatencyMs: number;
  p95LatencyMs: number;
  p99LatencyMs: number;
}

export interface PerformanceAlert {
  id: string;
  severity: 'info' | 'warning' | 'critical';
  category: string;
  message: string;
  timestamp: number;
  resolvedAt?: number;
}

// ===== PERFORMANCE DASHBOARD =====

class PerformanceDashboard {
  private startTime = Date.now();
  private requestTimestamps: number[] = [];
  private latencies: number[] = [];
  private errors = 0;
  private alerts: PerformanceAlert[] = [];
  private maxAlerts = 100;
  private lastEventLoopCheck = 0;
  private lastEventLoopLag = 0;

  // Time series tracking (1-minute windows)
  private timeSeriesBuffer: Array<{
    timestamp: number;
    latencyMs: number;
    isError: boolean;
  }> = [];

  /**
   * Record a request for time series analysis.
   */
  recordRequest(latencyMs: number, isError: boolean = false): void {
    const now = Date.now();
    this.requestTimestamps.push(now);
    this.latencies.push(latencyMs);
    if (isError) this.errors++;

    this.timeSeriesBuffer.push({ timestamp: now, latencyMs, isError });

    // Trim old data (keep last 5 minutes)
    const cutoff = now - 300_000;
    this.requestTimestamps = this.requestTimestamps.filter(t => t > cutoff);
    this.latencies = this.latencies.slice(-1000);
    this.timeSeriesBuffer = this.timeSeriesBuffer.filter(e => e.timestamp > cutoff);

    // Check for performance alerts
    this.checkAlerts(latencyMs, isError);
  }

  /**
   * Get a comprehensive dashboard snapshot.
   */
  getSnapshot(): DashboardSnapshot {
    const now = Date.now();

    return {
      timestamp: now,
      uptime: now - this.startTime,
      system: this.getSystemMetrics(),
      governor: this.getGovernorMetrics(),
      writeQueue: this.getWriteQueueMetrics(),
      vectorStore: this.getVectorMetrics(),
      health: this.getHealthMetrics(),
      timeSeries: this.getTimeSeriesMetrics(),
    };
  }

  /**
   * Get system-level metrics.
   */
  private getSystemMetrics(): SystemMetrics {
    const usage = process.memoryUsage();
    const usageMB = Math.round(usage.heapUsed / 1024 / 1024);
    const totalMB = Math.round(usage.heapTotal / 1024 / 1024);
    const percent = totalMB > 0 ? Math.round((usage.heapUsed / usage.heapTotal) * 100) : 0;

    // Event loop lag estimation
    const eventLoopLagMs = this.estimateEventLoopLag();

    // GC stats (if available via --expose-gc)
    let gcCount = 0;
    let gcTotalMs = 0;
    try {
      const gcStats = (globalThis as any).__gc_stats;
      if (gcStats) {
        gcCount = gcStats.count || 0;
        gcTotalMs = gcStats.totalMs || 0;
      }
    } catch {
      // GC stats not available
    }

    return {
      memoryUsageMB: usageMB,
      memoryTotalMB: totalMB,
      memoryPercent: percent,
      cpuUsagePercent: this.estimateCpuUsage(),
      eventLoopLagMs: eventLoopLagMs,
      gcCount,
      gcTotalMs,
      activeHandles: (process as any)._getActiveHandles?.()?.length ?? 0,
      activeRequests: (process as any)._getActiveRequests?.()?.length ?? 0,
    };
  }

  /**
   * Get ResourceGovernor metrics.
   */
  private getGovernorMetrics(): GovernorDashboardMetrics {
    try {
      const metrics = governor.getMetrics();
      const total = metrics.totalRequests || 1;
      return {
        totalRequests: metrics.totalRequests,
        rateLimited: metrics.rateLimited,
        rateLimitPercent: Math.round((metrics.rateLimited / total) * 10000) / 100,
        activeRequests: metrics.activeRequests,
        maxConcurrentRequests: metrics.maxActiveRequests || 50,
        concurrentUtilization: Math.round(
          (metrics.activeRequests / (metrics.maxActiveRequests || 50)) * 100
        ),
        memoryStatus: metrics.memoryStatus,
        dbStatus: metrics.dbStatus,
        circuitsOpen: metrics.circuitsOpen,
        rateLimiterBackend: metrics.rateLimiterBackend,
        circuitBreakerBackend: metrics.circuitBreakerBackend,
        writeQueueLength: metrics.writeQueueLength,
        writeLatencyMs: metrics.writeLatencyMs,
      };
    } catch {
      return this.getDefaultGovernorMetrics();
    }
  }

  private getDefaultGovernorMetrics(): GovernorDashboardMetrics {
    return {
      totalRequests: 0,
      rateLimited: 0,
      rateLimitPercent: 0,
      activeRequests: 0,
      maxConcurrentRequests: 50,
      concurrentUtilization: 0,
      memoryStatus: 'normal',
      dbStatus: 'healthy',
      circuitsOpen: 0,
      rateLimiterBackend: 'memory',
      circuitBreakerBackend: 'memory',
      writeQueueLength: 0,
      writeLatencyMs: 0,
    };
  }

  /**
   * Get WriteQueue metrics.
   */
  private getWriteQueueMetrics(): WriteQueueMetrics {
    try {
      // Import writeQueue dynamically to avoid circular dependencies
      const { writeQueue } = require('@/lib/write-queue');
      const stats = writeQueue.getStats();
      return {
        queueLength: stats.queueLength ?? 0,
        totalEnqueued: stats.enqueued ?? 0,
        totalFlushed: stats.flushed ?? 0,
        totalFailed: stats.failed ?? 0,
        avgWriteLatencyMs: stats.avgWriteLatencyMs ?? 0,
        walEnabled: stats.walEnabled ?? false,
        categories: stats.categories ?? {},
      };
    } catch {
      return {
        queueLength: 0,
        totalEnqueued: 0,
        totalFlushed: 0,
        totalFailed: 0,
        avgWriteLatencyMs: 0,
        walEnabled: false,
        categories: {},
      };
    }
  }

  /**
   * Get VectorStore metrics.
   */
  private getVectorMetrics(): VectorDashboardMetrics {
    try {
      const stats = vectorStore.getStats();
      return {
        backend: stats.backend,
        totalEmbeddings: stats.totalEmbeddings,
        dimensions: stats.dimensions,
        avgSearchLatencyMs: stats.avgSearchLatencyMs,
        totalSearches: stats.searches,
        totalInserts: stats.inserts,
        hnswM: stats.hnswM ?? 16,
        hnswEfConstruction: stats.hnswEfConstruction ?? 64,
      };
    } catch {
      return {
        backend: 'none',
        totalEmbeddings: 0,
        dimensions: 384,
        avgSearchLatencyMs: 0,
        totalSearches: 0,
        totalInserts: 0,
        hnswM: 16,
        hnswEfConstruction: 64,
      };
    }
  }

  /**
   * Get health check metrics.
   */
  private getHealthMetrics(): HealthDashboardMetrics {
    try {
      const governorMetrics = governor.getMetrics();
      const isCritical = governorMetrics.memoryStatus === 'critical' ||
                         governorMetrics.dbStatus === 'critical';

      return {
        status: isCritical ? 'unhealthy' :
                governorMetrics.memoryStatus === 'warning' ||
                governorMetrics.dbStatus === 'degraded' ? 'degraded' : 'healthy',
        checks: {
          memory: {
            status: governorMetrics.memoryStatus,
            message: `${governorMetrics.memoryPercent}% heap usage`,
            latencyMs: 0,
          },
          database: {
            status: governorMetrics.dbStatus,
            message: `Latency: ${governorMetrics.writeLatencyMs}ms, Queue: ${governorMetrics.writeQueueLength}`,
            latencyMs: governorMetrics.writeLatencyMs,
          },
          circuitBreakers: {
            status: governorMetrics.circuitsOpen > 0 ? 'warning' : 'healthy',
            message: `${governorMetrics.circuitsOpen} circuits open`,
            latencyMs: 0,
          },
          rateLimiter: {
            status: 'healthy',
            message: `Backend: ${governorMetrics.rateLimiterBackend}`,
            latencyMs: 0,
          },
        },
        lastCheckedAt: Date.now(),
      };
    } catch {
      return {
        status: 'unknown',
        checks: {},
        lastCheckedAt: Date.now(),
      };
    }
  }

  /**
   * Get time series metrics (1-minute window).
   */
  private getTimeSeriesMetrics(): TimeSeriesBucket {
    const now = Date.now();
    const oneMinuteAgo = now - 60_000;

    const recentEntries = this.timeSeriesBuffer.filter(e => e.timestamp > oneMinuteAgo);

    if (recentEntries.length === 0) {
      return {
        requestsPerSecond: 0,
        avgLatencyMs: 0,
        errorRate: 0,
        p50LatencyMs: 0,
        p95LatencyMs: 0,
        p99LatencyMs: 0,
      };
    }

    const latencies = recentEntries.map(e => e.latencyMs).sort((a, b) => a - b);
    const errorCount = recentEntries.filter(e => e.isError).length;

    return {
      requestsPerSecond: Math.round((recentEntries.length / 60) * 100) / 100,
      avgLatencyMs: Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length),
      errorRate: Math.round((errorCount / recentEntries.length) * 10000) / 100,
      p50LatencyMs: latencies[Math.floor(latencies.length * 0.5)] ?? 0,
      p95LatencyMs: latencies[Math.floor(latencies.length * 0.95)] ?? 0,
      p99LatencyMs: latencies[Math.floor(latencies.length * 0.99)] ?? 0,
    };
  }

  /**
   * Check for performance anomalies and generate alerts.
   */
  private checkAlerts(latencyMs: number, isError: boolean): void {
    const now = Date.now();

    // High latency alert
    if (latencyMs > 5000) {
      this.addAlert({
        id: `latency-${now}`,
        severity: 'critical',
        category: 'latency',
        message: `Request latency ${latencyMs}ms exceeds 5s threshold`,
        timestamp: now,
      });
    } else if (latencyMs > 1000) {
      this.addAlert({
        id: `latency-${now}`,
        severity: 'warning',
        category: 'latency',
        message: `Request latency ${latencyMs}ms exceeds 1s threshold`,
        timestamp: now,
      });
    }

    // Error rate alert
    if (isError && this.timeSeriesBuffer.length > 10) {
      const recent = this.timeSeriesBuffer.filter(e => e.timestamp > now - 60_000);
      const recentErrors = recent.filter(e => e.isError).length;
      const errorRate = recentErrors / recent.length;
      if (errorRate > 0.1) {
        this.addAlert({
          id: `error-rate-${now}`,
          severity: 'critical',
          category: 'errors',
          message: `Error rate ${(errorRate * 100).toFixed(1)}% exceeds 10% threshold`,
          timestamp: now,
        });
      }
    }
  }

  private addAlert(alert: PerformanceAlert): void {
    // Deduplicate: don't add same category+severity within 30 seconds
    const recent = this.alerts.find(
      a => a.category === alert.category &&
           a.severity === alert.severity &&
           now() - a.timestamp < 30_000
    );
    if (recent) return;

    this.alerts.push(alert);
    if (this.alerts.length > this.maxAlerts) {
      this.alerts = this.alerts.slice(-this.maxAlerts);
    }
  }

  /**
   * Get all active alerts.
   */
  getAlerts(): PerformanceAlert[] {
    const now = Date.now();
    // Auto-resolve alerts older than 5 minutes
    return this.alerts.map(a => {
      if (!a.resolvedAt && now - a.timestamp > 300_000) {
        return { ...a, resolvedAt: now };
      }
      return a;
    });
  }

  /**
   * Estimate event loop lag using a simple check.
   */
  private estimateEventLoopLag(): number {
    const now = Date.now();
    // Only check every 5 seconds to avoid overhead
    if (now - this.lastEventLoopCheck < 5000) {
      return this.lastEventLoopLag;
    }

    this.lastEventLoopCheck = now;
    const start = performance.now();
    setImmediate(() => {
      this.lastEventLoopLag = Math.round(performance.now() - start);
    });

    return this.lastEventLoopLag;
  }

  /**
   * Estimate CPU usage (simplified).
   */
  private estimateCpuUsage(): number {
    const usage = process.cpuUsage();
    // Convert to percentage (very rough estimate)
    const totalUs = usage.user + usage.system;
    const elapsedMs = Date.now() - this.startTime;
    if (elapsedMs === 0) return 0;
    return Math.min(100, Math.round((totalUs / 1000 / elapsedMs) * 100));
  }
}

// Helper for alert deduplication
function now(): number { return Date.now(); }

// ===== Singleton =====

const globalForDashboard = globalThis as unknown as {
  performanceDashboard: PerformanceDashboard | undefined;
};

export const performanceDashboard =
  globalForDashboard.performanceDashboard ??
  new PerformanceDashboard();

if (process.env.NODE_ENV !== 'production') {
  globalForDashboard.performanceDashboard = performanceDashboard;
}
