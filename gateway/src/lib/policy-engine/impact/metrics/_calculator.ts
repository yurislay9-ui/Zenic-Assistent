// ─── Zenic-Agents v3 — Impact Metrics Calculator ────────────────────────
// Extracted analysis-step helpers that were inlined in the original
// analyzeImpact function body (metrics.ts continuation section).
//
// These functions decompose the remaining steps of analyzeImpact into
// testable, self-contained units that accept all needed context as
// parameters instead of relying on closure scope.

import type {
  PolicyEffectV2,
  PolicyDocument,
} from "../types";
import type {
  ImpactAnalysisDepth,
  DependencyRef,
  AffectedSetRef,
  AffectedPlaybookRef,
  AffectedToolRef,
  BlastRadius,
  DownstreamChange,
} from "../types";
import {
  ImpactAnalysisDepth as ImpactAnalysisDepthValues,
  DependencyType as DependencyTypeValues,
} from "../types";

// ─── Tool Reference Processing ──────────────────────────────────────────

/** Result of processing tool references */
export interface ToolReferenceResult {
  toolRefsMap: Map<string, AffectedToolRef>;
  /** Tool nodes to be visited by the collector */
  toolNodes: Array<{
    id: string;
    type: "tool";
    name: string;
    dependencyType: typeof DependencyTypeValues.PROTECTED_BY;
    hardDependency: boolean;
    data: AffectedToolRef;
  }>;
}

/**
 * Build AffectedToolRef entries from raw protected-tools query results.
 * Deduplicates by toolId.
 */
export function buildToolReferences(
  protectedTools: Array<{
    toolId: string;
    toolName: string;
    riskLevel: string;
    accessPolicyEffect: string;
  }>,
): ToolReferenceResult {
  const toolRefsMap = new Map<string, AffectedToolRef>();
  const toolNodes: ToolReferenceResult["toolNodes"] = [];

  for (const tool of protectedTools) {
    if (toolRefsMap.has(tool.toolId)) continue;

    const currentVerdict = (tool.accessPolicyEffect as PolicyEffectV2) || "deny";
    const toolRef: AffectedToolRef = {
      toolId: tool.toolId,
      name: tool.toolName,
      riskLevel: tool.riskLevel,
      currentVerdict,
      predictedVerdict: undefined,
    };

    toolRefsMap.set(tool.toolId, toolRef);
    toolNodes.push({
      id: tool.toolId,
      type: "tool",
      name: tool.toolName,
      dependencyType: DependencyTypeValues.PROTECTED_BY,
      hardDependency: true,
      data: toolRef,
    });
  }

  return { toolRefsMap, toolNodes };
}

// ─── Indirect Dependency Helpers ────────────────────────────────────────

/** Strategy parameters for indirect dependency discovery */
export interface IndirectStrategy {
  includeIndirect: boolean;
  maxIndirectionLevels: number;
  includeComplianceChanges: boolean;
}

/**
 * Update predicted verdicts on affected tools based on downstream changes.
 */
export function applyPredictedVerdicts(
  affectedTools: AffectedToolRef[],
  downstreamChanges: DownstreamChange[],
): void {
  for (const change of downstreamChanges) {
    const toolRef = affectedTools.find(
      (t) => `tool:${t.toolId}` === change.request,
    );
    if (toolRef) {
      toolRef.predictedVerdict = change.predictedEffect;
    }
  }
}

/**
 * Update compliance score changes for affected playbooks based on
 * the policy's role in each playbook.
 */
export function applyComplianceScoreChanges(
  policyId: string,
  referencingPlaybooks: Array<{ playbookId: string; policies: string }>,
  affectedPlaybooks: AffectedPlaybookRef[],
): void {
  for (const pbRef of affectedPlaybooks) {
    const policyRefs = referencingPlaybooks.find(
      (pb) => pb.playbookId === pbRef.playbookId,
    );
    if (policyRefs) {
      const refs = JSON.parse(policyRefs.policies) as Array<{
        policyId: string;
        role?: string;
      }>;
      const thisRef = refs.find((r) => r.policyId === policyId);
      pbRef.complianceScoreChange = thisRef?.role === "required" ? -10 : -5;
    }
  }
}

// ─── Blast Radius & Result Building ─────────────────────────────────────

/** Parameters for building the final analysis result */
export interface AnalysisResultParams {
  policyId: string;
  proposedVersion: string | undefined;
  depth: ImpactAnalysisDepth;
  directDepRefs: DependencyRef[];
  indirectDepRefs: DependencyRef[];
  affectedSets: AffectedSetRef[];
  affectedPlaybooks: AffectedPlaybookRef[];
  affectedTools: AffectedToolRef[];
  downstreamChanges: DownstreamChange[];
  blastRadius: BlastRadius;
  requestedBy: string;
}

/**
 * Build the summary string for an impact analysis result.
 * Delegates to buildSummary from _formatters.
 */
export async function buildAnalysisSummary(
  params: Omit<AnalysisResultParams, "requestedBy">,
): Promise<string> {
  const { buildSummary } = await import("./_formatters");
  return buildSummary(
    params.policyId,
    params.depth,
    params.directDepRefs.length,
    params.indirectDepRefs.length,
    params.affectedSets.length,
    params.affectedPlaybooks.length,
    params.affectedTools.length,
    params.downstreamChanges,
    params.blastRadius,
  );
}
