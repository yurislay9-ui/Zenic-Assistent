// ─── Zenic-Agents v3 — Playbook Metrics Collector: Core Collection ────
// Core metric collection functions: collectPlaybookMetrics, getPlaybookMetricsHistory,
// and their supporting helpers.

import { db } from "@/lib/db";
import type {
  PlaybookMetricsSnapshot,
  PlaybookOperationalMetrics,
  RoiMetricsSnapshot,
  RoiCalculation,
  Industry,
} from "../types";
import { calculateRoi, getIndustryRoiFormula } from "../roi-calculator";
import {
  METRICS_LOOKBACK_MS,
  DEFAULT_HOURLY_RATE_USD,
  emptyRoiCalculation,
  round2,
  safeParseJson,
} from "./types";

// Re-export helpers for external consumers that imported them from the old file
export { emptyRoiCalculation, round2, safeParseJson } from "./types";

// ─── Core Collection ───────────────────────────────────────────────

/**
 * Collect operational metrics for a specific playbook.
 *
 * Queries ToolExecution for this playbook's activated tools,
 * computes live metrics, calculates ROI from current data,
 * and persists a snapshot to the database.
 */
export async function collectPlaybookMetrics(
  playbookDbId: string,
  tenantId?: string,
): Promise<PlaybookMetricsSnapshot> {
  try {
    // ─── 1. Load playbook and activation ────────────────────────────
    const playbook = await db.playbook.findUnique({
      where: { id: playbookDbId },
      include: {
        activations: {
          where: {
            status: "active",
            ...(tenantId ? { tenantId } : {}),
          },
        },
      },
    });

    if (!playbook) {
      throw new Error(`Playbook not found: ${playbookDbId}`);
    }

    // ─── 2. Resolve configured tool IDs from activations ────────────
    const configuredToolIds: string[] = [];
    for (const activation of playbook.activations) {
      try {
        const tools = JSON.parse(activation.configuredTools) as string[];
        if (Array.isArray(tools)) {
          configuredToolIds.push(...tools);
        }
      } catch {
        // Skip malformed JSON
      }
    }

    // Deduplicate tool IDs
    const uniqueToolIds = [...new Set(configuredToolIds)];

    // ─── 3. Query ToolExecution for metrics ─────────────────────────
    const now = new Date();
    const lookbackStart = new Date(now.getTime() - METRICS_LOOKBACK_MS);

    const [
      completedExecutions,
      deniedExecutions,
      conditionalExecutions,
      durationExecutions,
    ] = uniqueToolIds.length > 0
      ? await Promise.all([
          // actions_automated_daily: completed executions last 24h
          db.toolExecution.count({
            where: {
              toolId: { in: uniqueToolIds },
              status: "completed",
              createdAt: { gte: lookbackStart, lte: now },
            },
          }),

          // safety_gate_blocks: denied executions last 24h
          db.toolExecution.count({
            where: {
              toolId: { in: uniqueToolIds },
              verdict: "deny",
              createdAt: { gte: lookbackStart, lte: now },
            },
          }),

          // approval_requests: conditional executions last 24h
          db.toolExecution.count({
            where: {
              toolId: { in: uniqueToolIds },
              verdict: "conditional",
              createdAt: { gte: lookbackStart, lte: now },
            },
          }),

          // avg_decision_latency_ms: avg duration of completed executions
          db.toolExecution.findMany({
            where: {
              toolId: { in: uniqueToolIds },
              status: "completed",
              duration: { not: null },
              createdAt: { gte: lookbackStart, lte: now },
            },
            select: { duration: true },
          }),
        ])
      : [0, 0, 0, []];

    // ─── 4. Compute operational metrics ─────────────────────────────
    const durations = durationExecutions
      .map((e) => e.duration)
      .filter((d): d is number => d != null);
    const avgDecisionLatencyMs = durations.length > 0
      ? durations.reduce((sum, d) => sum + d, 0) / durations.length
      : 0;

    // ─── 5. Compute compliance score from policy test results ──────
    const complianceScore = await computeComplianceScore(playbook.policies);

    const operational: PlaybookOperationalMetrics = {
      actions_automated_daily: completedExecutions,
      safety_gate_blocks: deniedExecutions,
      approval_requests: conditionalExecutions,
      avg_decision_latency_ms: round2(avgDecisionLatencyMs),
      compliance_score: complianceScore,
    };

    // ─── 6. Calculate live ROI from metrics ────────────────────────
    const roiConfig = safeParseJson<{
      baseline: {
        manual_time_per_action_min: number;
        error_rate_pct: number;
        actions_per_month: number;
        cost_per_error_usd: number;
        violations_per_year: number;
        penalty_per_violation_usd: number;
      };
      projected: {
        automated_time_per_action_min: number;
        reduced_error_rate_pct: number;
        compliance_score_target: number;
        automation_rate_pct: number;
      };
      assumptions?: string[];
    }>(playbook.roiConfig);

    const roiCalculation = (roiConfig.baseline && roiConfig.projected)
      ? calculateRoi(
          roiConfig as Parameters<typeof calculateRoi>[0],
          getIndustryRoiFormula(playbook.industry as Industry),
        )
      : emptyRoiCalculation();

    // ─── 7. Compute ROI metrics snapshot (actual vs projected) ─────
    const roiSnapshot: RoiMetricsSnapshot = {
      actual_time_saved_hours: operational.actions_automated_daily * 30 * 0.1, // estimate: ~6 min saved per automated action
      actual_error_reduction_pct: roiConfig.projected
        ? Math.max(0, roiConfig.baseline.error_rate_pct - roiConfig.projected.reduced_error_rate_pct)
        : 0,
      actual_compliance_score: complianceScore,
      actual_automation_rate_pct: roiConfig.projected
        ? Math.min(100, (operational.actions_automated_daily * 30 / Math.max(1, roiConfig.baseline?.actions_per_month ?? 1)) * 100)
        : 0,
      revenue_impact_usd: round2(roiCalculation.net_roi_usd / 12),
      cost_savings_usd: round2(
        (operational.actions_automated_daily * 30 * 0.1 * DEFAULT_HOURLY_RATE_USD) +
        (operational.safety_gate_blocks * (roiConfig.baseline?.cost_per_error_usd ?? 0)),
      ),
      period_start: lookbackStart.toISOString(),
      period_end: now.toISOString(),
    };

    // ─── 8. Compute uptime ─────────────────────────────────────────
    const uptimePct = await computeUptimePercentage(uniqueToolIds, lookbackStart, now);

    // ─── 9. Persist snapshot ───────────────────────────────────────
    const snapshot = await db.playbookMetricsSnapshot.create({
      data: {
        playbookDbId,
        tenantId: tenantId ?? null,
        operational: JSON.stringify(operational),
        roi: JSON.stringify(roiCalculation),
        uptimePct,
        capturedAt: now,
      },
    });

    // ─── 10. Return typed snapshot ─────────────────────────────────
    return {
      playbookId: playbook.playbookId,
      capturedAt: snapshot.capturedAt.toISOString(),
      operational,
      roi: roiSnapshot,
      uptime_pct: uptimePct,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    throw new Error(`Failed to collect playbook metrics for ${playbookDbId}: ${message}`);
  }
}

/**
 * Get historical metrics snapshots for a playbook.
 * Returns snapshots from the last N days (default: 30).
 */
export async function getPlaybookMetricsHistory(
  playbookDbId: string,
  days: number = 30,
): Promise<PlaybookMetricsSnapshot[]> {
  try {
    const cutoff = new Date(Date.now() - days * 24 * 60 * 60 * 1000);

    const snapshots = await db.playbookMetricsSnapshot.findMany({
      where: {
        playbookDbId,
        capturedAt: { gte: cutoff },
      },
      orderBy: { capturedAt: "desc" },
    });

    return snapshots.map((s) => {
      const operational = safeParseJson<PlaybookOperationalMetrics>(s.operational);
      const roi = safeParseJson<RoiCalculation>(s.roi);

      // Build the ROI metrics snapshot from stored data
      const roiSnapshot: RoiMetricsSnapshot = {
        actual_time_saved_hours: operational.actions_automated_daily * 30 * 0.1,
        actual_error_reduction_pct: 0,
        actual_compliance_score: operational.compliance_score,
        actual_automation_rate_pct: 0,
        revenue_impact_usd: round2(roi.net_roi_usd / 12),
        cost_savings_usd: round2(
          (operational.actions_automated_daily * 30 * 0.1 * DEFAULT_HOURLY_RATE_USD),
        ),
        period_start: s.capturedAt.toISOString(),
        period_end: s.capturedAt.toISOString(),
      };

      return {
        playbookId: playbookDbId,
        capturedAt: s.capturedAt.toISOString(),
        operational,
        roi: roiSnapshot,
        uptime_pct: s.uptimePct,
      };
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    throw new Error(`Failed to get metrics history for playbook ${playbookDbId}: ${message}`);
  }
}

// ─── Helper Functions ───────────────────────────────────────────────

/**
 * Compute compliance score from policy test results.
 * Averages the pass rates of all test suites for policies linked to this playbook.
 */
async function computeComplianceScore(policiesJson: string): Promise<number> {
  try {
    const policies = JSON.parse(policiesJson) as Array<{ policyId: string; required: boolean }>;
    if (!Array.isArray(policies) || policies.length === 0) {
      return 100; // No policies = full compliance by default
    }

    const policyIds = policies.map((p) => p.policyId);

    // Get the latest test result for each policy
    const testResults = await db.declPolicyTestResult.findMany({
      where: {
        policyId: { in: policyIds },
      },
      orderBy: { createdAt: "desc" },
      distinct: ["policyId"],
    });

    if (testResults.length === 0) {
      return 100; // No test results = assume compliant
    }

    // Average pass rate across all policies
    const avgPassRate = testResults.reduce((sum, r) => {
      const total = r.totalTests || 1;
      return sum + (r.passed / total);
    }, 0) / testResults.length;

    return round2(avgPassRate * 100);
  } catch {
    return 100;
  }
}

/**
 * Compute uptime percentage for the configured tools.
 * Based on completed vs failed executions in the time window.
 */
async function computeUptimePercentage(
  toolIds: string[],
  since: Date,
  until: Date,
): Promise<number> {
  if (toolIds.length === 0) return 99.9;

  try {
    const [total, failed] = await Promise.all([
      db.toolExecution.count({
        where: {
          toolId: { in: toolIds },
          createdAt: { gte: since, lte: until },
        },
      }),
      db.toolExecution.count({
        where: {
          toolId: { in: toolIds },
          status: "failed",
          createdAt: { gte: since, lte: until },
        },
      }),
    ]);

    if (total === 0) return 99.9; // No data = assume healthy

    return round2(((total - failed) / total) * 100);
  } catch {
    return 99.9;
  }
}
