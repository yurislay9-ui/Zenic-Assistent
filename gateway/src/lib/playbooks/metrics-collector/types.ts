// ─── Zenic-Agents v3 — Playbook Metrics Collector: Types ─────────────
// Shared types and constants for the metrics-collector module.

import type {
  PlaybookMetricsSnapshot,
  PlaybookOperationalMetrics,
  RoiMetricsSnapshot,
  RoiCalculation,
  Industry,
} from "../types";

// Re-export from parent types so consumers don't break
export type {
  PlaybookMetricsSnapshot,
  PlaybookOperationalMetrics,
  RoiMetricsSnapshot,
  RoiCalculation,
  Industry,
};

// ─── Industry Metrics Summary Type ──────────────────────────────────

/** Aggregated metrics across all playbooks in an industry */
export interface IndustryMetricsSummary {
  /** Industry name */
  industry: string;
  /** Number of playbooks in this industry */
  playbookCount: number;
  /** Number of active activations across all playbooks */
  totalActivations: number;
  /** Average actions automated daily across playbooks */
  avgActionsAutomatedDaily: number;
  /** Average safety gate blocks daily */
  avgSafetyGateBlocks: number;
  /** Average approval requests daily */
  avgApprovalRequests: number;
  /** Average decision latency in ms */
  avgDecisionLatencyMs: number;
  /** Average compliance score (0-100) */
  avgComplianceScore: number;
  /** Average uptime percentage */
  avgUptimePct: number;
  /** Total actions automated daily across all playbooks */
  totalActionsAutomatedDaily: number;
  /** Total safety gate blocks daily */
  totalSafetyGateBlocks: number;
  /** Average ROI percentage across playbooks */
  avgRoiPercentage: number;
  /** Total net ROI in USD across all playbooks */
  totalNetRoiUsd: number;
  /** When this summary was computed (ISO 8601) */
  computedAt: string;
}

// ─── Constants ──────────────────────────────────────────────────────

/** Default lookback window for operational metrics (24 hours) */
export const METRICS_LOOKBACK_MS = 24 * 60 * 60 * 1000;

/** Default hourly rate for live ROI computation */
export const DEFAULT_HOURLY_RATE_USD = 50;

// ─── Shared Helper Functions ────────────────────────────────────────

/** Return an empty ROI calculation with zero values */
export function emptyRoiCalculation(): RoiCalculation {
  return {
    time_saved_hours_month: 0,
    errors_avoided_month: 0,
    compliance_risk_reduction_usd: 0,
    net_roi_usd: 0,
    roi_percentage: 0,
    payback_months: 0,
  };
}

/** Round a number to 2 decimal places */
export function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

/** Safely parse JSON with fallback to empty object */
export function safeParseJson<T>(json: string | null | undefined): T {
  try {
    if (!json) return {} as T;
    return JSON.parse(json) as T;
  } catch {
    return {} as T;
  }
}
