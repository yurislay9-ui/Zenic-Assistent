// ─── Zenic-Agents v3 — Playbook Metrics Collector: Aggregation ───────
// Industry-wide metric aggregation and seeding functions.

import { db } from "@/lib/db";
import type {
  PlaybookOperationalMetrics,
  RoiCalculation,
} from "../types";
import type { IndustryMetricsSummary } from "./types";
import { round2, safeParseJson } from "./types";

/**
 * Aggregate metrics across all playbooks in an industry.
 * Returns averages and totals for the industry.
 */
export async function aggregateIndustryMetrics(
  industry: string,
): Promise<IndustryMetricsSummary> {
  try {
    // Find all playbooks in this industry
    const playbooks = await db.playbook.findMany({
      where: { industry, isActive: true },
      include: {
        activations: { where: { status: "active" } },
        metricsSnapshots: {
          orderBy: { capturedAt: "desc" },
          take: 1,
        },
      },
    });

    // Count total active activations
    const totalActivations = playbooks.reduce(
      (sum, p) => sum + p.activations.length,
      0,
    );

    // Collect latest operational metrics from each playbook's most recent snapshot
    const operationalMetrics: PlaybookOperationalMetrics[] = [];
    const roiCalculations: RoiCalculation[] = [];
    const uptimeValues: number[] = [];

    for (const playbook of playbooks) {
      const latestSnapshot = playbook.metricsSnapshots[0];
      if (latestSnapshot) {
        const op = safeParseJson<PlaybookOperationalMetrics>(latestSnapshot.operational);
        const roi = safeParseJson<RoiCalculation>(latestSnapshot.roi);
        operationalMetrics.push(op);
        roiCalculations.push(roi);
        uptimeValues.push(latestSnapshot.uptimePct);
      }
    }

    // Compute averages
    const count = operationalMetrics.length || 1; // Avoid division by zero

    const avgActionsAutomatedDaily = operationalMetrics.length > 0
      ? operationalMetrics.reduce((sum, m) => sum + m.actions_automated_daily, 0) / count
      : 0;

    const avgSafetyGateBlocks = operationalMetrics.length > 0
      ? operationalMetrics.reduce((sum, m) => sum + m.safety_gate_blocks, 0) / count
      : 0;

    const avgApprovalRequests = operationalMetrics.length > 0
      ? operationalMetrics.reduce((sum, m) => sum + m.approval_requests, 0) / count
      : 0;

    const avgDecisionLatencyMs = operationalMetrics.length > 0
      ? operationalMetrics.reduce((sum, m) => sum + m.avg_decision_latency_ms, 0) / count
      : 0;

    const avgComplianceScore = operationalMetrics.length > 0
      ? operationalMetrics.reduce((sum, m) => sum + m.compliance_score, 0) / count
      : 0;

    const avgUptimePct = uptimeValues.length > 0
      ? uptimeValues.reduce((sum, u) => sum + u, 0) / uptimeValues.length
      : 99.9;

    const avgRoiPercentage = roiCalculations.length > 0
      ? roiCalculations.reduce((sum, r) => sum + r.roi_percentage, 0) / roiCalculations.length
      : 0;

    const totalNetRoiUsd = roiCalculations.reduce((sum, r) => sum + r.net_roi_usd, 0);

    return {
      industry,
      playbookCount: playbooks.length,
      totalActivations,
      avgActionsAutomatedDaily: round2(avgActionsAutomatedDaily),
      avgSafetyGateBlocks: round2(avgSafetyGateBlocks),
      avgApprovalRequests: round2(avgApprovalRequests),
      avgDecisionLatencyMs: round2(avgDecisionLatencyMs),
      avgComplianceScore: round2(avgComplianceScore),
      avgUptimePct: round2(avgUptimePct),
      totalActionsAutomatedDaily: round2(
        operationalMetrics.reduce((sum, m) => sum + m.actions_automated_daily, 0),
      ),
      totalSafetyGateBlocks: round2(
        operationalMetrics.reduce((sum, m) => sum + m.safety_gate_blocks, 0),
      ),
      avgRoiPercentage: round2(avgRoiPercentage),
      totalNetRoiUsd: round2(totalNetRoiUsd),
      computedAt: new Date().toISOString(),
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    throw new Error(`Failed to aggregate industry metrics for ${industry}: ${message}`);
  }
}

/**
 * Seed default metric configurations for playbooks.
 * Creates initial metric snapshot entries for active playbooks that
 * don't yet have any metrics data.
 *
 * @returns Number of playbooks seeded
 */
export async function seedPlaybookMetrics(): Promise<number> {
  try {
    // Find active playbooks without any metrics snapshots
    const activePlaybooks = await db.playbook.findMany({
      where: {
        isActive: true,
        metricsSnapshots: { none: {} },
      },
    });

    let seeded = 0;

    for (const playbook of activePlaybooks) {
      const operational: PlaybookOperationalMetrics = {
        actions_automated_daily: 0,
        safety_gate_blocks: 0,
        approval_requests: 0,
        avg_decision_latency_ms: 0,
        compliance_score: 100, // Start with perfect compliance
      };

      const roiCalculation = { time_saved_hours_month: 0, errors_avoided_month: 0, compliance_risk_reduction_usd: 0, net_roi_usd: 0, roi_percentage: 0, payback_months: 0 };

      await db.playbookMetricsSnapshot.create({
        data: {
          playbookDbId: playbook.id,
          operational: JSON.stringify(operational),
          roi: JSON.stringify(roiCalculation),
          uptimePct: 100.0,
          capturedAt: new Date(),
        },
      });

      seeded++;
    }

    return seeded;
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    throw new Error(`Failed to seed playbook metrics: ${message}`);
  }
}
