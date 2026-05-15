// ─── Zenic-Agents v3 — Security Metrics Service ─────────────────────
// Phase 2: Safety gate blocks, risk distribution, compliance violations,
// tampering attempts, unauthorized access
//
// Computed from: AuditLog + ToolExecution tables via Prisma

import { db } from "@/lib/db";
import type { SecurityMetrics, MetricSummary, MetricTimeRange } from "../types/metrics";
import { METRIC_NAMES } from "../types";

/**
 * Compute security metrics from audit and execution data.
 * Focuses on threat detection, access control, and compliance.
 */
export async function collectSecurityMetrics(
  timeRange?: MetricTimeRange,
): Promise<SecurityMetrics> {
  const now = new Date();
  const from = resolveTimeRange(timeRange, now);
  const to = timeRange?.to === "now" ? now : (timeRange?.to ? new Date(timeRange.to) : now);

  // ─── Base Queries ──────────────────────────────────────────────────

  const [
    deniedActions,
    riskLevels,
    complianceEvents,
    tamperEvents,
    unauthorizedEvents,
    safetyGateBlocks,
    allExecutions,
  ] = await Promise.all([
    // Denied actions by category
    db.auditLog.findMany({
      where: { createdAt: { gte: from, lte: to }, outcome: "denied" },
      select: { action: true, resource: true, details: true },
    }),

    // Risk level distribution from tool executions
    db.toolExecution.findMany({
      where: { createdAt: { gte: from, lte: to } },
      select: { verdict: true, toolId: true },
    }),

    // Compliance-related audit entries (severity: error/critical)
    db.auditLog.count({
      where: {
        createdAt: { gte: from, lte: to },
        severity: { in: ["error", "critical"] },
        resource: { in: ["policy", "tool", "role"] },
      },
    }),

    // Tampering/integrity violation events
    db.auditLog.count({
      where: {
        createdAt: { gte: from, lte: to },
        action: { contains: "tamper" },
      },
    }),

    // Unauthorized access attempts
    db.auditLog.count({
      where: {
        createdAt: { gte: from, lte: to },
        outcome: "denied",
        action: { contains: "auth" },
      },
    }),

    // Safety gate blocks (RBAC denials)
    db.auditLog.count({
      where: {
        createdAt: { gte: from, lte: to },
        action: { in: ["tool.execute", "gateway.rbac_check"] },
        outcome: "denied",
      },
    }),

    // All executions for total count
    db.toolExecution.count({
      where: { createdAt: { gte: from, lte: to } },
    }),
  ]);

  // ─── Compute Metrics ───────────────────────────────────────────────

  // Risk distribution from verdicts
  const riskDistribution: Record<string, number> = { low: 0, medium: 0, high: 0, critical: 0 };
  for (const exec of riskLevels) {
    // Infer risk from verdict: deny→high risk, conditional→medium, allow→low
    if (exec.verdict === "deny") {
      riskDistribution["high"]++;
    } else if (exec.verdict === "conditional") {
      riskDistribution["medium"]++;
    } else {
      riskDistribution["low"]++;
    }
  }

  // Top blocked categories
  const blockedByCategory = new Map<string, number>();
  for (const action of deniedActions) {
    const cat = action.resource ?? "unknown";
    blockedByCategory.set(cat, (blockedByCategory.get(cat) ?? 0) + 1);
  }
  const topBlockedCategories = Array.from(blockedByCategory.entries())
    .map(([category, count]) => ({ category, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 10);

  // Security score: 100 - (weighted penalties)
  const denyRate = allExecutions > 0 ? (deniedActions.length / allExecutions) * 100 : 0;
  const tamperRate = allExecutions > 0 ? (tamperEvents / allExecutions) * 100 : 0;
  const securityScore = Math.max(0, Math.min(100, 100 - (denyRate * 0.3 + tamperRate * 2 + complianceEvents * 0.5)));

  return {
    safetyGateBlocks: buildSummary(METRIC_NAMES.SAFETY_GATE_BLOCKS, "security", "count", safetyGateBlocks),
    riskDistribution,
    complianceViolations: buildSummary(METRIC_NAMES.COMPLIANCE_VIOLATIONS, "security", "count", complianceEvents),
    tamperingAttempts: buildSummary(METRIC_NAMES.TAMPERING_ATTEMPTS, "security", "count", tamperEvents),
    unauthorizedAccess: buildSummary(METRIC_NAMES.UNAUTHORIZED_ACCESS, "security", "count", unauthorizedEvents),
    securityScore: Math.round(securityScore),
    topBlockedCategories,
  };
}

// ─── Helpers ────────────────────────────────────────────────────────

function buildSummary(
  name: string,
  category: string,
  unit: string,
  current: number,
): MetricSummary {
  return {
    name,
    category: category as MetricSummary["category"],
    unit: unit as MetricSummary["unit"],
    current: round2(current),
    min: round2(current * 0.8),
    max: round2(current * 1.2),
    avg: round2(current),
    sum: round2(current),
    count: 1,
    trend: "flat" as const,
    changePercent: 0,
  };
}

function resolveTimeRange(timeRange: MetricTimeRange | undefined, now: Date): Date {
  if (!timeRange) return new Date(now.getTime() - 24 * 60 * 60 * 1000);

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
