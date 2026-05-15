// ─── Zenic-Agents v3 — Export Type System ────────────────────────────
// Phase 2: OpenTelemetry + JSON export format types

// ─── Enum-like Constants ────────────────────────────────────────────

/** Supported export formats */
export const ExportFormat = {
  OTLP_JSON: "otlp_json",
  OTLP_HTTP: "otlp_http",
  JSON: "json",
} as const;
export type ExportFormat = (typeof ExportFormat)[keyof typeof ExportFormat];

// ─── OpenTelemetry Types (OTLP compatible) ──────────────────────────

/** OTLP Span — OpenTelemetry Protocol span representation */
export interface OtelSpan {
  /** Unique span ID (hex) */
  spanId: string;
  /** Trace ID (hex) */
  traceId: string;
  /** Parent span ID (hex) — empty string if root */
  parentSpanId: string;
  /** Span name */
  name: string;
  /** Span kind: 1=INTERNAL, 2=SERVER, 3=CLIENT, 4=PRODUCER, 5=CONSUMER */
  kind: number;
  /** Start time in nanoseconds since epoch */
  startTimeUnixNano: string;
  /** End time in nanoseconds since epoch */
  endTimeUnixNano: string;
  /** Span attributes */
  attributes?: Array<{ key: string; value: { stringValue?: string; intValue?: string; doubleValue?: number } }>;
  /** Span status */
  status?: { code: number; message?: string };
  /** Span events */
  events?: Array<{
    timeUnixNano: string;
    name: string;
    attributes?: Array<{ key: string; value: { stringValue?: string } }>;
  }>;
  /** Span links */
  links?: Array<{
    traceId: string;
    spanId: string;
    attributes?: Array<{ key: string; value: { stringValue?: string } }>;
  }>;
}

/** OTLP Resource Spans — grouped by resource */
export interface OtelResourceSpan {
  /** Resource attributes (service.name, service.version, etc.) */
  resource: {
    attributes: Array<{ key: string; value: { stringValue: string } }>;
  };
  /** Scope spans — grouped by instrumentation scope */
  scopeSpans: Array<{
    scope: { name: string; version?: string };
    spans: OtelSpan[];
  }>;
}

/** OTLP Export Payload — top-level OTLP JSON structure */
export interface OtelExportPayload {
  /** Resource spans */
  resourceSpans: OtelResourceSpan[];
}

// ─── JSON Export Types ──────────────────────────────────────────────

/** JSON export — single trace with spans */
export interface JsonTraceExport {
  traceId: string;
  sessionId?: string | null;
  decisionId?: string | null;
  status: string;
  verdict?: string | null;
  duration?: number | null;
  spanCount: number;
  createdAt: string;
  completedAt?: string | null;
  spans: Array<{
    spanId: string;
    parentSpanId?: string | null;
    name: string;
    kind: string;
    status: string;
    duration?: number | null;
    resource?: string | null;
    resourceId?: string | null;
    action?: string | null;
    outcome?: string | null;
    attributes: Record<string, unknown>;
    startTime: string;
    endTime?: string | null;
  }>;
}

/** JSON export — metric summary */
export interface JsonMetricExport {
  name: string;
  category: string;
  unit: string;
  description: string;
  current: number;
  min: number;
  max: number;
  avg: number;
  trend: "up" | "down" | "flat";
  points: Array<{
    value: number;
    labels: Record<string, string>;
    timestamp: string;
  }>;
}

/** Full JSON export payload */
export interface JsonExportPayload {
  /** Export metadata */
  meta: {
    exportedAt: string;
    format: "json";
    version: "1.0.0";
    service: string;
  };
  /** Traces */
  traces: JsonTraceExport[];
  /** Metrics */
  metrics: JsonMetricExport[];
}

/** Parameters for export requests */
export interface ExportQueryParams {
  /** Export format */
  format: ExportFormat;
  /** Filter by trace IDs */
  traceIds?: string[];
  /** Filter by session ID */
  sessionId?: string;
  /** Filter by time range */
  startDate?: string;
  endDate?: string;
  /** Include metrics in export */
  includeMetrics?: boolean;
  /** Include traces in export */
  includeTraces?: boolean;
  /** Maximum number of traces to export */
  limit?: number;
}
