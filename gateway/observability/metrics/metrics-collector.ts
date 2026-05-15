// ─── Zenic-Agents v3 — Metrics Collector (Aggregator) ───────────────
// Phase 2: Central metrics aggregation — combines business, security,
// and resilience metrics into unified ObservabilityMetrics.
// Also handles MetricSeries + MetricPoint persistence.

import { db } from "@/lib/db";
import type { ObservabilityMetrics, MetricTimeRange, MetricCategory, MetricsQueryParams, MetricSeriesWithPoints, MetricSeriesRecord, MetricPointRecord } from "../types/metrics";
import { DEFAULT_METRIC_SERIES } from "../types";
import { collectBusinessMetrics } from "./business-metrics";
import { collectSecurityMetrics } from "./security-metrics";
import { collectResilienceMetrics } from "./resilience-metrics";

// ─── Aggregation ────────────────────────────────────────────────────

/**
 * Collect all observability metrics — business + security + resilience.
 * This is the main entry point for metric collection.
 */
export async function collectAllMetrics(
  timeRange?: MetricTimeRange,
): Promise<ObservabilityMetrics> {
  const [business, security, resilience] = await Promise.all([
    collectBusinessMetrics(timeRange),
    collectSecurityMetrics(timeRange),
    collectResilienceMetrics(timeRange),
  ]);

  return {
    business,
    security,
    resilience,
    computedAt: new Date().toISOString(),
    timeRange: timeRange ?? { from: "24h", to: "now" },
  };
}

/**
 * Collect metrics for a specific category.
 */
export async function collectMetricsByCategory(
  category: MetricCategory,
  timeRange?: MetricTimeRange,
): Promise<ObservabilityMetrics> {
  switch (category) {
    case "business":
      return {
        business: await collectBusinessMetrics(timeRange),
        security: emptySecurityMetrics(),
        resilience: emptyResilienceMetrics(),
        computedAt: new Date().toISOString(),
        timeRange: timeRange ?? { from: "24h", to: "now" },
      };
    case "security":
      return {
        business: emptyBusinessMetrics(),
        security: await collectSecurityMetrics(timeRange),
        resilience: emptyResilienceMetrics(),
        computedAt: new Date().toISOString(),
        timeRange: timeRange ?? { from: "24h", to: "now" },
      };
    case "resilience":
      return {
        business: emptyBusinessMetrics(),
        security: emptySecurityMetrics(),
        resilience: await collectResilienceMetrics(timeRange),
        computedAt: new Date().toISOString(),
        timeRange: timeRange ?? { from: "24h", to: "now" },
      };
    default:
      return collectAllMetrics(timeRange);
  }
}

// ─── Metric Series Persistence ──────────────────────────────────────

/**
 * Seed the default metric series into the database.
 * Idempotent — uses upsert by name.
 */
export async function seedMetricSeries(): Promise<number> {
  let created = 0;

  for (const series of DEFAULT_METRIC_SERIES) {
    await db.metricSeries.upsert({
      where: { name: series.name },
      update: {
        description: series.description,
        category: series.category,
        unit: series.unit,
        labels: JSON.stringify(series.labels),
      },
      create: {
        name: series.name,
        description: series.description,
        category: series.category,
        unit: series.unit,
        labels: JSON.stringify(series.labels),
      },
    });
    created++;
  }

  return created;
}

/**
 * Record a metric data point.
 * Creates the series if it doesn't exist (auto-registration).
 */
export async function recordMetricPoint(params: {
  name: string;
  value: number;
  labels?: Record<string, string>;
  timestamp?: Date;
  category?: MetricCategory;
  description?: string;
  unit?: string;
}): Promise<void> {
  // Ensure series exists
  const series = await db.metricSeries.upsert({
    where: { name: params.name },
    update: {},
    create: {
      name: params.name,
      description: params.description ?? `Auto-registered metric: ${params.name}`,
      category: params.category ?? "operational",
      unit: params.unit ?? "count",
      labels: "{}",
    },
  });

  // Create the data point
  await db.metricPoint.create({
    data: {
      seriesId: series.id,
      value: params.value,
      labels: JSON.stringify(params.labels ?? {}),
      timestamp: params.timestamp ?? new Date(),
    },
  });
}

/**
 * Query metric series with optional filters.
 */
export async function queryMetricSeries(
  params: MetricsQueryParams = {},
): Promise<{
  series: MetricSeriesWithPoints[];
  total: number;
  page: number;
  pageSize: number;
}> {
  const {
    category, names, includePoints = false, maxPoints = 100,
    page = 1, pageSize = 20,
  } = params;

  const where: Record<string, unknown> = {};
  if (category) where.category = category;
  if (names && names.length > 0) where.name = { in: names };

  const [rawSeries, total] = await Promise.all([
    db.metricSeries.findMany({
      where,
      skip: (page - 1) * pageSize,
      take: pageSize,
      orderBy: { name: "asc" },
      include: includePoints
        ? {
            points: {
              orderBy: { timestamp: "desc" },
              take: maxPoints,
            },
          }
        : false,
    }),
    db.metricSeries.count({ where }),
  ]);

  const series: MetricSeriesWithPoints[] = rawSeries.map((s) => ({
    id: s.id,
    name: s.name,
    description: s.description,
    category: s.category as MetricCategory,
    unit: s.unit as MetricSeriesRecord["unit"],
    labels: safeParseJson<Record<string, string>>(s.labels),
    createdAt: s.createdAt,
    updatedAt: s.updatedAt,
    points: includePoints && "points" in s
      ? (s.points as Array<{ id: string; seriesId: string; value: number; labels: string; timestamp: Date; createdAt: Date }>).map(mapPoint)
      : [],
  }));

  return { series, total, page, pageSize };
}

/**
 * Get latest metric values for all series in a category.
 */
export async function getLatestMetrics(
  category?: MetricCategory,
): Promise<Array<MetricSeriesRecord & { latestValue: number | null; latestTimestamp: Date | null }>> {
  const seriesList = await db.metricSeries.findMany({
    where: category ? { category } : {},
    orderBy: { name: "asc" },
    include: {
      points: {
        orderBy: { timestamp: "desc" },
        take: 1,
      },
    },
  });

  return seriesList.map((s) => ({
    id: s.id,
    name: s.name,
    description: s.description,
    category: s.category as MetricCategory,
    unit: s.unit as MetricSeriesRecord["unit"],
    labels: safeParseJson<Record<string, string>>(s.labels),
    createdAt: s.createdAt,
    updatedAt: s.updatedAt,
    latestValue: s.points.length > 0 ? s.points[0].value : null,
    latestTimestamp: s.points.length > 0 ? s.points[0].timestamp : null,
  }));
}

// ─── Mapper ─────────────────────────────────────────────────────────

function mapPoint(raw: { id: string; seriesId: string; value: number; labels: string; timestamp: Date; createdAt: Date }): MetricPointRecord {
  return {
    id: raw.id,
    seriesId: raw.seriesId,
    value: raw.value,
    labels: safeParseJson<Record<string, string>>(raw.labels),
    timestamp: raw.timestamp,
    createdAt: raw.createdAt,
  };
}

function safeParseJson<T>(json: string): T {
  try { return JSON.parse(json) as T; }
  catch { return {} as T; }
}

// ─── Empty Placeholders ─────────────────────────────────────────────

function emptyBusinessMetrics(): import("../types/metrics").BusinessMetrics {
  const empty = buildEmptySummary;
  return {
    denyRate: empty("business.deny_rate"),
    approvalRate: empty("business.approval_rate"),
    costPerFlow: empty("business.cost_per_flow"),
    timeToDecision: empty("business.time_to_decision_ms"),
    automationSavings: empty("business.automation_savings_hours"),
    executionThroughput: empty("business.execution_throughput"),
    totalExecutions: 0,
    totalDenied: 0,
    totalConditional: 0,
    totalAllowed: 0,
  };
}

function emptySecurityMetrics(): import("../types/metrics").SecurityMetrics {
  const empty = buildEmptySummary;
  return {
    safetyGateBlocks: empty("security.safety_gate_blocks"),
    riskDistribution: { low: 0, medium: 0, high: 0, critical: 0 },
    complianceViolations: empty("security.compliance_violations"),
    tamperingAttempts: empty("security.tampering_attempts"),
    unauthorizedAccess: empty("security.unauthorized_access"),
    securityScore: 100,
    topBlockedCategories: [],
  };
}

function emptyResilienceMetrics(): import("../types/metrics").ResilienceMetrics {
  const empty = buildEmptySummary;
  return {
    rollbackRate: empty("resilience.rollback_rate"),
    circuitBreakerOpens: empty("resilience.circuit_breaker_opens"),
    fallbackRate: empty("resilience.fallback_rate"),
    errorRate: empty("resilience.error_rate"),
    mttr: 0,
    uptimePercent: 100,
  };
}

function buildEmptySummary(name: string): import("../types/metrics").MetricSummary {
  return {
    name,
    category: "business",
    unit: "count",
    current: 0,
    min: 0,
    max: 0,
    avg: 0,
    sum: 0,
    count: 0,
    trend: "flat",
    changePercent: 0,
  };
}
