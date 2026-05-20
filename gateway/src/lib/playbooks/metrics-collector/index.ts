// ─── Zenic-Agents v3 — Playbook Metrics Collector: Index ──────────────
// Re-exports all public API from the metrics-collector sub-modules.

// Types
export type { IndustryMetricsSummary } from "./types";
export {
  METRICS_LOOKBACK_MS,
  DEFAULT_HOURLY_RATE_USD,
  emptyRoiCalculation,
  round2,
  safeParseJson,
} from "./types";

// Core collection
export {
  collectPlaybookMetrics,
  getPlaybookMetricsHistory,
} from "./_collector";

// Aggregation
export {
  aggregateIndustryMetrics,
  seedPlaybookMetrics,
} from "./_aggregator";
