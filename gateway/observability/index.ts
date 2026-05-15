// ─── Zenic-Agents v3 — Observability Barrel Export ──────────────────
// Phase 2: Complete observability — traces, metrics, export
// Public API — import anything from '@/lib/observability'

// ─── Types ───────────────────────────────────────────────────────────
export {
  OBSERVABILITY_SERVICE,
  SPAN_PREFIXES,
  METRIC_NAMES,
  METRIC_CATEGORIES,
  DEFAULT_METRIC_SERIES,
} from "./types";
export type { MetricName, MetricCategory as MetricCategoryType } from "./types";

export type {
  TraceStatus,
  SpanKind,
  SpanStatus,
  TraceRecord,
  SpanRecord,
  TraceWithSpans,
  TraceQueryParams,
  SpanEvent,
  SpanLink,
  SpanCreateParams,
  SpanCompleteParams,
} from "./types/tracing";

export type {
  MetricCategory,
  MetricUnit,
  MetricSeriesRecord,
  MetricPointRecord,
  MetricSeriesWithPoints,
  MetricsQueryParams,
  MetricTimeRange,
  MetricSummary,
  BusinessMetrics,
  SecurityMetrics,
  ResilienceMetrics,
  ObservabilityMetrics,
} from "./types/metrics";

export type {
  ExportFormat,
  OtelSpan,
  OtelResourceSpan,
  OtelExportPayload,
  JsonExportPayload,
  JsonTraceExport,
  JsonMetricExport,
  ExportQueryParams,
} from "./types/export";

// ─── Tracing ────────────────────────────────────────────────────────
export { SpanBuilder, ActiveSpanHandle, getActiveSpanCount } from "./tracing";
export { TraceCollector, getTraceCollector, resetTraceCollector } from "./tracing";
export type { TraceCreateParams } from "./tracing";

// ─── Metrics ────────────────────────────────────────────────────────
export { collectBusinessMetrics } from "./metrics";
export { collectSecurityMetrics } from "./metrics";
export { collectResilienceMetrics } from "./metrics";
export {
  collectAllMetrics,
  collectMetricsByCategory,
  seedMetricSeries,
  recordMetricPoint,
  queryMetricSeries,
  getLatestMetrics,
} from "./metrics";

// ─── Export ─────────────────────────────────────────────────────────
export { exportOtel } from "./export";
export { exportJson } from "./export";
