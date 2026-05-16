// ─── Zenic-Agents v3 — Observability Type System ────────────────────
// Phase 2: Distributed Tracing + Metrics + Export types
// Philosophy: "Complete observability — every decision, every span, every metric"

// ─── Re-export from sub-modules ─────────────────────────────────────

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
} from "./tracing";

export type {
  MetricCategory,
  MetricUnit,
  MetricSeriesRecord,
  MetricPointRecord,
  MetricSeriesWithPoints,
  MetricsQueryParams,
  MetricTimeRange,
} from "./metrics";

export type {
  ExportFormat,
  OtelSpan,
  OtelResourceSpan,
  OtelExportPayload,
  JsonExportPayload,
  JsonTraceExport,
  JsonMetricExport,
  ExportQueryParams,
} from "./export";

// ─── Shared Constants ───────────────────────────────────────────────

/** Observability service name */
export const OBSERVABILITY_SERVICE = "zenic-gateway" as const;

/** Span name prefixes — maps to gateway pipeline steps */
export const SPAN_PREFIXES = {
  GATEWAY: "gateway",
  TOOL_RESOLUTION: "gateway.tool_resolution",
  AUTH_CHECK: "gateway.auth_check",
  RATE_LIMIT: "gateway.rate_limit",
  RBAC_CHECK: "gateway.rbac_check",
  RISK_POLICY: "gateway.risk_policy",
  TOOL_EXECUTE: "gateway.tool_execution",
  MERKLE_AUDIT: "gateway.merkle_audit",
} as const;

/** Metric series names — business, security, resilience */
export const METRIC_NAMES = {
  // Business
  DENY_RATE: "business.deny_rate",
  APPROVAL_RATE: "business.approval_rate",
  COST_PER_FLOW: "business.cost_per_flow",
  TIME_TO_DECISION: "business.time_to_decision_ms",
  AUTOMATION_SAVINGS: "business.automation_savings_hours",
  EXECUTION_THROUGHPUT: "business.execution_throughput",

  // Security
  SAFETY_GATE_BLOCKS: "security.safety_gate_blocks",
  RISK_SCORE_DISTRIBUTION: "security.risk_score_distribution",
  COMPLIANCE_VIOLATIONS: "security.compliance_violations",
  TAMPERING_ATTEMPTS: "security.tampering_attempts",
  UNAUTHORIZED_ACCESS: "security.unauthorized_access",

  // Resilience
  ROLLBACK_RATE: "resilience.rollback_rate",
  CIRCUIT_BREAKER_OPENS: "resilience.circuit_breaker_opens",
  FALLBACK_RATE: "resilience.fallback_rate",
  ERROR_RATE: "resilience.error_rate",

  // Operational
  GATEWAY_LATENCY: "operational.gateway_latency_ms",
  TOOL_EXECUTION_DURATION: "operational.tool_execution_duration_ms",
  ACTIVE_SESSIONS: "operational.active_sessions",
  RATE_LIMIT_HITS: "operational.rate_limit_hits",
} as const;

export type MetricName = (typeof METRIC_NAMES)[keyof typeof METRIC_NAMES];

/** Metric categories */
export const METRIC_CATEGORIES = {
  BUSINESS: "business",
  SECURITY: "security",
  RESILIENCE: "resilience",
  OPERATIONAL: "operational",
} as const;

export type MetricCategory = (typeof METRIC_CATEGORIES)[keyof typeof METRIC_CATEGORIES];

/** Default metric series to seed */
export const DEFAULT_METRIC_SERIES: Array<{
  name: string;
  description: string;
  category: MetricCategory;
  unit: string;
  labels: Record<string, string>;
}> = [
  // Business
  { name: METRIC_NAMES.DENY_RATE, description: "Rate of DENY verdicts per time window", category: "business", unit: "percent", labels: { dimension: "verdict" } },
  { name: METRIC_NAMES.APPROVAL_RATE, description: "Rate of conditional→approved executions", category: "business", unit: "percent", labels: { dimension: "approval" } },
  { name: METRIC_NAMES.COST_PER_FLOW, description: "Estimated cost per decision flow (time × resources)", category: "business", unit: "ms", labels: { dimension: "cost" } },
  { name: METRIC_NAMES.TIME_TO_DECISION, description: "Average time from request to verdict", category: "business", unit: "ms", labels: { dimension: "latency" } },
  { name: METRIC_NAMES.AUTOMATION_SAVINGS, description: "Estimated hours saved by automated decisions", category: "business", unit: "count", labels: { dimension: "savings" } },
  { name: METRIC_NAMES.EXECUTION_THROUGHPUT, description: "Number of tool executions per minute", category: "business", unit: "count", labels: { dimension: "throughput" } },

  // Security
  { name: METRIC_NAMES.SAFETY_GATE_BLOCKS, description: "Safety gate blocks by category", category: "security", unit: "count", labels: { dimension: "safety" } },
  { name: METRIC_NAMES.RISK_SCORE_DISTRIBUTION, description: "Distribution of risk scores across executions", category: "security", unit: "count", labels: { dimension: "risk" } },
  { name: METRIC_NAMES.COMPLIANCE_VIOLATIONS, description: "Compliance violations by standard", category: "security", unit: "count", labels: { dimension: "compliance" } },
  { name: METRIC_NAMES.TAMPERING_ATTEMPTS, description: "Detected tampering or integrity violation attempts", category: "security", unit: "count", labels: { dimension: "integrity" } },
  { name: METRIC_NAMES.UNAUTHORIZED_ACCESS, description: "Unauthorized access attempts by source", category: "security", unit: "count", labels: { dimension: "auth" } },

  // Resilience
  { name: METRIC_NAMES.ROLLBACK_RATE, description: "Rate of operation rollbacks", category: "resilience", unit: "percent", labels: { dimension: "recovery" } },
  { name: METRIC_NAMES.CIRCUIT_BREAKER_OPENS, description: "Circuit breaker open events per tool/service", category: "resilience", unit: "count", labels: { dimension: "circuit" } },
  { name: METRIC_NAMES.FALLBACK_RATE, description: "Fallback activation rate per agent/component", category: "resilience", unit: "percent", labels: { dimension: "degradation" } },
  { name: METRIC_NAMES.ERROR_RATE, description: "Error rate across all operations", category: "resilience", unit: "percent", labels: { dimension: "errors" } },

  // Operational
  { name: METRIC_NAMES.GATEWAY_LATENCY, description: "End-to-end gateway pipeline latency", category: "operational", unit: "ms", labels: { dimension: "latency" } },
  { name: METRIC_NAMES.TOOL_EXECUTION_DURATION, description: "Individual tool execution duration", category: "operational", unit: "ms", labels: { dimension: "duration" } },
  { name: METRIC_NAMES.ACTIVE_SESSIONS, description: "Number of active decision sessions", category: "operational", unit: "count", labels: { dimension: "sessions" } },
  { name: METRIC_NAMES.RATE_LIMIT_HITS, description: "Rate limit threshold hits per tool/tenant", category: "operational", unit: "count", labels: { dimension: "throttle" } },
];
