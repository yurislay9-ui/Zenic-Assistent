// ─── Zenic-Agents v3 — JSON Exporter ────────────────────────────────
// Phase 2: JSON format export for dashboards and custom integrations
//
// Strategy Pattern — one of multiple export strategies.
// Produces clean, human-readable JSON with traces and metrics.

import { db } from "@/lib/db";
import type { JsonExportPayload, JsonTraceExport, JsonMetricExport, ExportQueryParams } from "../types/export";
import type { TraceRecord, SpanRecord } from "../types/tracing";
import { OBSERVABILITY_SERVICE } from "../types";
import { collectAllMetrics } from "../metrics/metrics-collector";

// ─── JSON Export ────────────────────────────────────────────────────

/**
 * Export observability data in clean JSON format.
 * Includes both traces and metrics in a single payload.
 */
export async function exportJson(params: ExportQueryParams): Promise<JsonExportPayload> {
  const [traces, metrics] = await Promise.all([
    params.includeTraces !== false ? fetchTracesJson(params) : [],
    params.includeMetrics !== false ? fetchMetricsJson(params) : [],
  ]);

  return {
    meta: {
      exportedAt: new Date().toISOString(),
      format: "json",
      version: "1.0.0",
      service: OBSERVABILITY_SERVICE,
    },
    traces,
    metrics,
  };
}

// ─── Trace Export ───────────────────────────────────────────────────

async function fetchTracesJson(params: ExportQueryParams): Promise<JsonTraceExport[]> {
  const where: Record<string, unknown> = {};

  if (params.traceIds && params.traceIds.length > 0) {
    where.traceId = { in: params.traceIds };
  }
  if (params.sessionId) {
    where.sessionId = params.sessionId;
  }
  if (params.startDate || params.endDate) {
    const createdAt: Record<string, Date> = {};
    if (params.startDate) createdAt.gte = new Date(params.startDate);
    if (params.endDate) createdAt.lte = new Date(params.endDate);
    where.createdAt = createdAt;
  }

  const limit = params.limit ?? 100;

  const rawTraces = await db.trace.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: limit,
    include: {
      spans: { orderBy: { startTime: "asc" } },
    },
  });

  return rawTraces.map((trace) => ({
    traceId: trace.traceId,
    sessionId: trace.sessionId,
    decisionId: trace.decisionId,
    status: trace.status,
    verdict: trace.verdict,
    duration: trace.duration,
    spanCount: trace.spanCount,
    createdAt: trace.createdAt.toISOString(),
    completedAt: trace.completedAt?.toISOString() ?? null,
    spans: trace.spans.map((span) => ({
      spanId: span.spanId,
      parentSpanId: span.parentSpanId,
      name: span.name,
      kind: span.kind,
      status: span.status,
      duration: span.duration,
      resource: span.resource,
      resourceId: span.resourceId,
      action: span.action,
      outcome: span.outcome,
      attributes: safeParseJson<Record<string, unknown>>(span.attributes),
      startTime: span.startTime.toISOString(),
      endTime: span.endTime?.toISOString() ?? null,
    })),
  }));
}

// ─── Metrics Export ─────────────────────────────────────────────────

async function fetchMetricsJson(_params: ExportQueryParams): Promise<JsonMetricExport[]> {
  // Get all metric series with latest points
  const series = await db.metricSeries.findMany({
    orderBy: { name: "asc" },
    include: {
      points: {
        orderBy: { timestamp: "desc" },
        take: 100,
      },
    },
  });

  if (series.length === 0) {
    // Compute live metrics and export
    const liveMetrics = await collectAllMetrics();
    return computeJsonMetricsFromLive(liveMetrics);
  }

  return series.map((s) => {
    const points = s.points;
    const values = points.map((p) => p.value);

    return {
      name: s.name,
      category: s.category,
      unit: s.unit,
      description: s.description,
      current: values.length > 0 ? values[0] : 0,
      min: values.length > 0 ? Math.min(...values) : 0,
      max: values.length > 0 ? Math.max(...values) : 0,
      avg: values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : 0,
      trend: computeTrend(values) as "up" | "down" | "flat",
      points: points.map((p) => ({
        value: p.value,
        labels: safeParseJson<Record<string, string>>(p.labels),
        timestamp: p.timestamp.toISOString(),
      })),
    };
  });
}

// ─── Helpers ────────────────────────────────────────────────────────

function computeJsonMetricsFromLive(
  live: Awaited<ReturnType<typeof collectAllMetrics>>,
): JsonMetricExport[] {
  const metrics: JsonMetricExport[] = [];

  // Business metrics
  const bizMetrics: Array<{ name: string; summary: import("../types/metrics").MetricSummary }> = [
    { name: "business.deny_rate", summary: live.business.denyRate },
    { name: "business.approval_rate", summary: live.business.approvalRate },
    { name: "business.cost_per_flow", summary: live.business.costPerFlow },
    { name: "business.time_to_decision_ms", summary: live.business.timeToDecision },
    { name: "business.automation_savings_hours", summary: live.business.automationSavings },
    { name: "business.execution_throughput", summary: live.business.executionThroughput },
  ];

  for (const m of bizMetrics) {
    metrics.push(summaryToJson(m.name, "business", m.summary));
  }

  // Security metrics
  const secMetrics: Array<{ name: string; summary: import("../types/metrics").MetricSummary }> = [
    { name: "security.safety_gate_blocks", summary: live.security.safetyGateBlocks },
    { name: "security.compliance_violations", summary: live.security.complianceViolations },
    { name: "security.tampering_attempts", summary: live.security.tamperingAttempts },
    { name: "security.unauthorized_access", summary: live.security.unauthorizedAccess },
  ];

  for (const m of secMetrics) {
    metrics.push(summaryToJson(m.name, "security", m.summary));
  }

  // Resilience metrics
  const resMetrics: Array<{ name: string; summary: import("../types/metrics").MetricSummary }> = [
    { name: "resilience.rollback_rate", summary: live.resilience.rollbackRate },
    { name: "resilience.circuit_breaker_opens", summary: live.resilience.circuitBreakerOpens },
    { name: "resilience.fallback_rate", summary: live.resilience.fallbackRate },
    { name: "resilience.error_rate", summary: live.resilience.errorRate },
  ];

  for (const m of resMetrics) {
    metrics.push(summaryToJson(m.name, "resilience", m.summary));
  }

  return metrics;
}

function summaryToJson(
  name: string,
  category: string,
  summary: import("../types/metrics").MetricSummary,
): JsonMetricExport {
  return {
    name,
    category,
    unit: summary.unit,
    description: name,
    current: summary.current,
    min: summary.min,
    max: summary.max,
    avg: summary.avg,
    trend: summary.trend,
    points: [],
  };
}

function computeTrend(values: number[]): string {
  if (values.length < 2) return "flat";
  const recent = values.slice(0, Math.ceil(values.length / 2));
  const older = values.slice(Math.ceil(values.length / 2));
  const recentAvg = recent.reduce((a, b) => a + b, 0) / recent.length;
  const olderAvg = older.reduce((a, b) => a + b, 0) / older.length;
  const change = olderAvg > 0 ? ((recentAvg - olderAvg) / olderAvg) * 100 : 0;
  return change > 5 ? "up" : change < -5 ? "down" : "flat";
}

function safeParseJson<T>(json: string): T {
  try { return JSON.parse(json) as T; }
  catch { return {} as T; }
}
