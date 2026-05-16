// ─── Zenic-Agents v3 — Metrics Type System ──────────────────────────
// Phase 2: Business + Security + Resilience metrics types

// ─── Enum-like Constants ────────────────────────────────────────────

/** Metric categories — groups metrics by domain */
export const MetricCategory = {
  BUSINESS: "business",
  SECURITY: "security",
  RESILIENCE: "resilience",
  OPERATIONAL: "operational",
} as const;
export type MetricCategory = (typeof MetricCategory)[keyof typeof MetricCategory];

/** Metric units */
export const MetricUnit = {
  COUNT: "count",
  MILLISECONDS: "ms",
  PERCENT: "percent",
  USD: "usd",
  RATIO: "ratio",
} as const;
export type MetricUnit = (typeof MetricUnit)[keyof typeof MetricUnit];

// ─── Core Types ─────────────────────────────────────────────────────

/** A metric series — a named time series of observations */
export interface MetricSeriesRecord {
  id: string;
  name: string;
  description: string;
  category: MetricCategory;
  unit: MetricUnit;
  labels: Record<string, string>;
  createdAt: Date;
  updatedAt: Date;
}

/** A single data point in a metric series */
export interface MetricPointRecord {
  id: string;
  seriesId: string;
  value: number;
  labels: Record<string, string>;
  timestamp: Date;
  createdAt: Date;
}

/** Metric series with its recent data points */
export interface MetricSeriesWithPoints extends MetricSeriesRecord {
  points: MetricPointRecord[];
}

/** Time range for metric queries */
export interface MetricTimeRange {
  /** Start of the range (ISO 8601 or relative like "1h", "24h", "7d") */
  from: string;
  /** End of the range (ISO 8601 or "now") */
  to: string;
  /** Aggregation interval: "1m" | "5m" | "1h" | "1d" */
  interval?: string;
}

/** Parameters for querying metrics */
export interface MetricsQueryParams {
  /** Filter by category */
  category?: MetricCategory;
  /** Filter by metric name(s) */
  names?: string[];
  /** Time range */
  timeRange?: MetricTimeRange;
  /** Include data points in response */
  includePoints?: boolean;
  /** Maximum points per series */
  maxPoints?: number;
  /** Pagination: page number (1-based) */
  page?: number;
  /** Pagination: items per page */
  pageSize?: number;
}

// ─── Computed Metric Aggregates ─────────────────────────────────────

/** Summary statistics for a metric over a time window */
export interface MetricSummary {
  /** Metric series name */
  name: string;
  /** Category */
  category: MetricCategory;
  /** Unit */
  unit: MetricUnit;
  /** Current value (latest point) */
  current: number;
  /** Minimum value in the window */
  min: number;
  /** Maximum value in the window */
  max: number;
  /** Average value in the window */
  avg: number;
  /** Sum of all values in the window */
  sum: number;
  /** Number of data points */
  count: number;
  /** Trend direction: up | down | flat */
  trend: "up" | "down" | "flat";
  /** Percentage change from previous period */
  changePercent: number;
}

/** Business metrics aggregate — computed from ToolExecution + AuditLog */
export interface BusinessMetrics {
  /** DENY verdict rate as percentage */
  denyRate: MetricSummary;
  /** Approval rate (conditional→approved) as percentage */
  approvalRate: MetricSummary;
  /** Average cost per flow in ms (proxy for resource consumption) */
  costPerFlow: MetricSummary;
  /** Average time from request to verdict in ms */
  timeToDecision: MetricSummary;
  /** Estimated hours saved by automation */
  automationSavings: MetricSummary;
  /** Execution throughput (executions/minute) */
  executionThroughput: MetricSummary;
  /** Total executions in the period */
  totalExecutions: number;
  /** Total DENY verdicts in the period */
  totalDenied: number;
  /** Total conditional verdicts in the period */
  totalConditional: number;
  /** Total allow verdicts in the period */
  totalAllowed: number;
}

/** Security metrics aggregate — computed from AuditLog + safety events */
export interface SecurityMetrics {
  /** Safety gate blocks count */
  safetyGateBlocks: MetricSummary;
  /** Risk score distribution (counts per risk level) */
  riskDistribution: Record<string, number>;
  /** Compliance violations count */
  complianceViolations: MetricSummary;
  /** Tampering attempt count */
  tamperingAttempts: MetricSummary;
  /** Unauthorized access attempt count */
  unauthorizedAccess: MetricSummary;
  /** Overall security score (0-100) */
  securityScore: number;
  /** Top blocked categories */
  topBlockedCategories: Array<{ category: string; count: number }>;
}

/** Resilience metrics aggregate — computed from execution + fallback data */
export interface ResilienceMetrics {
  /** Rollback operation rate as percentage */
  rollbackRate: MetricSummary;
  /** Circuit breaker open events count */
  circuitBreakerOpens: MetricSummary;
  /** Fallback activation rate as percentage */
  fallbackRate: MetricSummary;
  /** Error rate across all operations */
  errorRate: MetricSummary;
  /** Mean time to recovery in ms */
  mttr: number;
  /** System uptime percentage */
  uptimePercent: number;
}

/** All metrics combined */
export interface ObservabilityMetrics {
  business: BusinessMetrics;
  security: SecurityMetrics;
  resilience: ResilienceMetrics;
  /** When these metrics were computed */
  computedAt: string;
  /** Time range these metrics cover */
  timeRange: MetricTimeRange;
}
