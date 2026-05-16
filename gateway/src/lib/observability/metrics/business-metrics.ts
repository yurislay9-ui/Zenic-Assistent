// ─── Zenic-Agents v3 — Business Metrics Service ─────────────────────
// Phase 2: DENY rate, approval rate, cost per flow, time to decision,
// automation savings, execution throughput
//
// Computed from: ToolExecution + AuditLog tables via Prisma

import { db } from "@/lib/db";
import type { BusinessMetrics, MetricSummary, MetricTimeRange } from "../types/metrics";
import { METRIC_NAMES } from "../types";

// ─── Business Metrics Collection ────────────────────────────────────

/**
 * Compute business metrics from execution and audit data.
 * All metrics are derived — no external data sources required.
 */
export async function collectBusinessMetrics(
  timeRange?: MetricTimeRange,
): Promise<BusinessMetrics> {
  const now = new Date();
  const from = resolveTimeRange(timeRange, now);
  const to = timeRange?.to === "now" ? now : (timeRange?.to ? new Date(timeRange.to) : now);

  // ─── Base Queries ──────────────────────────────────────────────────

  const [
    totalExecutions,
    totalAllowed,
    totalDenied,
    totalConditional,
    totalFailed,
    executionDurations,
    verdictDurations,
    recentExecutions,
    previousPeriodExecutions,
  ] = await Promise.all([
    // Total executions in period
    db.toolExecution.count({
      where: { createdAt: { gte: from, lte: to } },
    }),

    // Allow verdicts
    db.toolExecution.count({
      where: { createdAt: { gte: from, lte: to }, verdict: "allow" },
    }),

    // Deny verdicts
    db.toolExecution.count({
      where: { createdAt: { gte: from, lte: to }, verdict: "deny" },
    }),

    // Conditional verdicts
    db.toolExecution.count({
      where: { createdAt: { gte: from, lte: to }, verdict: "conditional" },
    }),

    // Failed executions
    db.toolExecution.count({
      where: { createdAt: { gte: from, lte: to }, status: "failed" },
    }),

    // Execution durations for cost calculation
    db.toolExecution.findMany({
      where: { createdAt: { gte: from, lte: to }, duration: { not: null } },
      select: { duration: true },
    }),

    // Verdict pipeline durations (from audit)
    db.auditLog.findMany({
      where: {
        createdAt: { gte: from, lte: to },
        action: { contains: "gateway" },
      },
      select: { details: true, createdAt: true },
    }),

    // Recent execution count for throughput
    db.toolExecution.count({
      where: {
        createdAt: {
          gte: new Date(to.getTime() - 60 * 1000), // Last 1 minute
          lte: to,
        },
      },
    }),

    // Previous period for trend calculation
    db.toolExecution.count({
      where: {
        createdAt: {
          gte: new Date(from.getTime() - (to.getTime() - from.getTime())),
          lt: from,
        },
      },
    }),
  ]);

  // ─── Compute Metrics ───────────────────────────────────────────────

  const durations = executionDurations
    .map((e) => e.duration)
    .filter((d): d is number => d != null);

  const avgDuration = durations.length > 0
    ? durations.reduce((sum, d) => sum + d, 0) / durations.length
    : 0;

  const denyRate = totalExecutions > 0
    ? (totalDenied / totalExecutions) * 100
    : 0;

  const approvalRate = totalConditional > 0
    ? // Approved = completed that were previously conditional
      ((totalAllowed > 0 ? 1 : 0) * 100) // Simplified: if any allowed, assume approved
    : 100; // No conditional = 100% auto-approved

  const costPerFlow = avgDuration; // Proxy: ms of compute time = cost

  const timeToDecision = avgDuration; // Time from request to verdict

  // Estimate automation savings: assume each automated decision saves ~5 min of manual review
  const automatedDecisions = totalAllowed + totalDenied; // All non-conditional
  const automationSavingsHours = (automatedDecisions * 5) / 60; // 5 min per decision → hours

  const periodMinutes = Math.max((to.getTime() - from.getTime()) / 60000, 1);
  const executionThroughput = totalExecutions / periodMinutes;

  // Trend calculation: compare with previous period
  const changePercent = previousPeriodExecutions > 0
    ? ((totalExecutions - previousPeriodExecutions) / previousPeriodExecutions) * 100
    : 0;

  const trend = changePercent > 5 ? "up" : changePercent < -5 ? "down" : "flat";

  return {
    denyRate: buildSummary(METRIC_NAMES.DENY_RATE, "business", "percent", denyRate, trend, changePercent),
    approvalRate: buildSummary(METRIC_NAMES.APPROVAL_RATE, "business", "percent", approvalRate, trend, changePercent),
    costPerFlow: buildSummary(METRIC_NAMES.COST_PER_FLOW, "business", "ms", costPerFlow, trend, changePercent),
    timeToDecision: buildSummary(METRIC_NAMES.TIME_TO_DECISION, "business", "ms", timeToDecision, trend, changePercent),
    automationSavings: buildSummary(METRIC_NAMES.AUTOMATION_SAVINGS, "business", "count", automationSavingsHours, trend, changePercent),
    executionThroughput: buildSummary(METRIC_NAMES.EXECUTION_THROUGHPUT, "business", "count", executionThroughput, trend, changePercent),
    totalExecutions,
    totalDenied,
    totalConditional,
    totalAllowed,
  };
}

// ─── Helper ─────────────────────────────────────────────────────────

function buildSummary(
  name: string,
  category: string,
  unit: string,
  current: number,
  trend: "up" | "down" | "flat",
  changePercent: number,
): MetricSummary {
  return {
    name,
    category: category as MetricSummary["category"],
    unit: unit as MetricSummary["unit"],
    current: round2(current),
    min: round2(current * 0.8), // Estimated from single-point
    max: round2(current * 1.2),
    avg: round2(current),
    sum: round2(current),
    count: 1,
    trend,
    changePercent: round2(changePercent),
  };
}

function resolveTimeRange(timeRange: MetricTimeRange | undefined, now: Date): Date {
  if (!timeRange) {
    // Default: last 24 hours
    return new Date(now.getTime() - 24 * 60 * 60 * 1000);
  }

  if (timeRange.from.includes("h") || timeRange.from.includes("d")) {
    const match = timeRange.from.match(/^(\d+)(h|d|m)$/);
    if (match) {
      const value = parseInt(match[1], 10);
      const unit = match[2];
      const ms = unit === "h" ? value * 3600000 : unit === "d" ? value * 86400000 : value * 60000;
      return new Date(now.getTime() - ms);
    }
  }

  return new Date(timeRange.from);
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}
