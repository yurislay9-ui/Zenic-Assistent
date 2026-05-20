// ─── Zenic-Agents v3 — Impact Metrics Formatters ────────────────────────
// Summary building, analysis retrieval, and listing functions.
// Split from metrics.ts for modularity.

import { db } from "@/lib/db";
import type {
  ImpactAnalysisDepth,
  ImpactAnalysisResult,
  DependencyRef,
  AffectedSetRef,
  AffectedPlaybookRef,
  AffectedToolRef,
  BlastRadius,
  DownstreamChange,
  SimulationRiskLevel,
} from "../types";

// ─── Summary Builder ───────────────────────────────────────────────────

export function buildSummary(
  policyId: string,
  depth: ImpactAnalysisDepth,
  directCount: number,
  indirectCount: number,
  setsCount: number,
  playbooksCount: number,
  toolsCount: number,
  changes: DownstreamChange[],
  blastRadius: BlastRadius,
): string {
  const allowToDeny = changes.filter(
    (c) => c.currentEffect === "allow" && c.predictedEffect === "deny",
  ).length;
  const denyToAllow = changes.filter(
    (c) => c.currentEffect === "deny" && c.predictedEffect === "allow",
  ).length;

  const lines: string[] = [
    `Impact Analysis for policy "${policyId}" (${depth} depth):`,
    `  Direct dependencies: ${directCount}`,
  ];

  if (indirectCount > 0) {
    lines.push(`  Indirect dependencies: ${indirectCount}`);
  }

  lines.push(
    `  Affected policy sets: ${setsCount}`,
    `  Affected playbooks: ${playbooksCount}`,
    `  Affected tools: ${toolsCount}`,
  );

  if (changes.length > 0) {
    lines.push(
      `  Verdict changes: ${changes.length} total`,
      `    ALLOW → DENY: ${allowToDeny}`,
      `    DENY → ALLOW: ${denyToAllow}`,
    );
  }

  lines.push(
    `  Risk score: ${blastRadius.riskScore}/100 (${blastRadius.riskLevel})`,
    `  Estimated recovery: ${blastRadius.estimatedRecoveryMinutes} minutes`,
  );

  return lines.join("\n");
}

// ─── getImpactAnalysis ─────────────────────────────────────────────────

/**
 * Load a previously stored impact analysis by analysisId.
 */
export async function getImpactAnalysis(
  analysisId: string,
): Promise<ImpactAnalysisResult | null> {
  try {
    const record = await db.policyImpactAnalysis.findUnique({
      where: { analysisId },
    });

    if (!record) return null;

    return {
      policyId: record.policyId,
      analyzedAt: record.createdAt.toISOString(),
      directDependencies: JSON.parse(record.directDependencies) as DependencyRef[],
      indirectDependencies: JSON.parse(record.indirectDependencies) as DependencyRef[],
      affectedSets: JSON.parse(record.affectedSets) as AffectedSetRef[],
      affectedPlaybooks: JSON.parse(record.affectedPlaybooks) as AffectedPlaybookRef[],
      affectedTools: JSON.parse(record.affectedTools) as AffectedToolRef[],
      blastRadius: JSON.parse(record.blastRadius) as BlastRadius,
      downstreamChanges: JSON.parse(record.downstreamChanges) as DownstreamChange[],
      summary: record.summary,
    };
  } catch (error) {
    console.error(`[ImpactAnalysis] Failed to load analysis ${analysisId}:`, error);
    return null;
  }
}

// ─── listImpactAnalyses ────────────────────────────────────────────────

/** A lightweight summary of an impact analysis */
export interface ImpactAnalysisSummary {
  /** Analysis ID */
  analysisId: string;
  /** Target policy ID */
  policyId: string;
  /** Analysis depth */
  depth: ImpactAnalysisDepth;
  /** Risk score */
  riskScore: number;
  /** Risk level */
  riskLevel: SimulationRiskLevel;
  /** Number of direct dependencies */
  directDependencyCount: number;
  /** Number of indirect dependencies */
  indirectDependencyCount: number;
  /** When analyzed */
  analyzedAt: string;
  /** Who requested */
  requestedBy: string;
  /** Summary */
  summary: string;
}

/**
 * List impact analyses, optionally filtered by policyId.
 */
export async function listImpactAnalyses(
  policyId?: string,
): Promise<ImpactAnalysisSummary[]> {
  try {
    const records = await db.policyImpactAnalysis.findMany({
      where: policyId ? { policyId } : undefined,
      orderBy: { createdAt: "desc" },
      take: 100,
    });

    return records.map((r) => {
      const blastRadius = JSON.parse(r.blastRadius) as BlastRadius;
      const directDeps = JSON.parse(r.directDependencies) as DependencyRef[];
      const indirectDeps = JSON.parse(r.indirectDependencies) as DependencyRef[];

      return {
        analysisId: r.analysisId,
        policyId: r.policyId,
        depth: r.analysisDepth as ImpactAnalysisDepth,
        riskScore: blastRadius.riskScore,
        riskLevel: blastRadius.riskLevel,
        directDependencyCount: directDeps.length,
        indirectDependencyCount: indirectDeps.length,
        analyzedAt: r.createdAt.toISOString(),
        requestedBy: r.requestedBy,
        summary: r.summary,
      };
    });
  } catch (error) {
    console.error("[ImpactAnalysis] Failed to list analyses:", error);
    return [];
  }
}
