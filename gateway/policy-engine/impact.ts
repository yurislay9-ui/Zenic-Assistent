// ─── Zenic-Agents v3 — Policy Impact Analysis Engine ────────────────────
// Phase 4: Declarative Versioned Policy Engine — Impact Analysis Module
//
// Analyzes the impact of changing a policy by:
//   1. Loading the target policy from DB
//   2. Finding direct and indirect dependencies (Visitor pattern)
//   3. Predicting downstream evaluation changes (Strategy pattern)
//   4. Calculating blast radius with risk scoring
//   5. Persisting analysis results to DB
//
// Design Patterns:
//   - Visitor: DependencyGraphVisitor traverses the dependency graph
//   - Strategy: DepthStrategy determines analysis depth (quick/standard/deep)
//   - Composite: DependencyNode composes dependency tree with children

import { db } from "@/lib/db";
import type {
  PolicyDocument,
  PolicyEffectV2,
} from "./types";
import type {
  ImpactAnalysisRequest,
  ImpactAnalysisDepth,
  ImpactAnalysisResult,
  DependencyRef,
  DependencyType,
  AffectedSetRef,
  AffectedPlaybookRef,
  AffectedToolRef,
  BlastRadius,
  ImpactCategory,
  DownstreamChange,
  SimulationRiskLevel,
  ConflictSeverity,
  PolicySetEntry,
} from "./types";
import {
  ImpactAnalysisDepth as ImpactAnalysisDepthValues,
  DependencyType as DependencyTypeValues,
  SimulationRiskLevel as SimulationRiskLevelValues,
  ConflictSeverity as ConflictSeverityValues,
} from "./types";

// ─── Composite: Dependency Node ─────────────────────────────────────────

/** A node in the dependency tree (Composite pattern) */
interface DependencyNode {
  /** Unique identifier for this node */
  id: string;
  /** Type of resource */
  type: "policy" | "policy_set" | "playbook" | "tool" | "approval";
  /** Human-readable name */
  name: string;
  /** Dependency type from parent */
  dependencyType: DependencyType;
  /** Whether this is a hard dependency */
  hardDependency: boolean;
  /** Child nodes (indirect dependencies) */
  children: DependencyNode[];
  /** Extra typed data attached to this node (e.g., AffectedSetRef, AffectedToolRef) */
  data?: unknown;
}

/** Build a DependencyRef from a DependencyNode */
function nodeToRef(node: DependencyNode): DependencyRef {
  return {
    id: node.id,
    type: node.type,
    name: node.name,
    dependencyType: node.dependencyType,
    hardDependency: node.hardDependency,
  };
}

// ─── Strategy: Depth Analysis Strategies ────────────────────────────────

/** Strategy interface for analysis depth */
interface DepthStrategy {
  /** Whether to include indirect dependencies */
  includeIndirect: boolean;
  /** Maximum levels of indirection (0 = direct only, -1 = unlimited) */
  maxIndirectionLevels: number;
  /** Whether to predict downstream tool verdict changes */
  predictToolChanges: boolean;
  /** Whether to include playbook compliance score changes */
  includeComplianceChanges: boolean;
}

/** Strategy configuration per analysis depth */
const DEPTH_STRATEGIES: Record<ImpactAnalysisDepth, DepthStrategy> = {
  [ImpactAnalysisDepthValues.QUICK]: {
    includeIndirect: false,
    maxIndirectionLevels: 0,
    predictToolChanges: true,
    includeComplianceChanges: false,
  },
  [ImpactAnalysisDepthValues.STANDARD]: {
    includeIndirect: true,
    maxIndirectionLevels: 1,
    predictToolChanges: true,
    includeComplianceChanges: true,
  },
  [ImpactAnalysisDepthValues.DEEP]: {
    includeIndirect: true,
    maxIndirectionLevels: -1, // unlimited — full transitive closure
    predictToolChanges: true,
    includeComplianceChanges: true,
  },
};

// ─── Visitor: Dependency Graph Visitor ──────────────────────────────────

/** Visitor interface for traversing the dependency graph */
interface DependencyVisitor {
  /** Called when visiting a direct dependency */
  visitDirect(node: DependencyNode): void;
  /** Called when visiting an indirect dependency */
  visitIndirect(node: DependencyNode): void;
}

/** Collecting visitor that gathers all visited nodes into categories */
class ImpactCollectorVisitor implements DependencyVisitor {
  readonly directDeps: DependencyNode[] = [];
  readonly indirectDeps: DependencyNode[] = [];
  readonly affectedSets: AffectedSetRef[] = [];
  readonly affectedPlaybooks: AffectedPlaybookRef[] = [];
  readonly affectedTools: AffectedToolRef[] = [];
  readonly affectedApprovals: DependencyRef[] = [];

  visitDirect(node: DependencyNode): void {
    this.directDeps.push(node);
    this.categorize(node);
  }

  visitIndirect(node: DependencyNode): void {
    this.indirectDeps.push(node);
    this.categorize(node);
  }

  private categorize(node: DependencyNode): void {
    switch (node.type) {
      case "policy_set":
        this.affectedSets.push(node.data as AffectedSetRef);
        break;
      case "playbook":
        this.affectedPlaybooks.push(node.data as AffectedPlaybookRef);
        break;
      case "tool":
        this.affectedTools.push(node.data as AffectedToolRef);
        break;
      case "approval":
        this.affectedApprovals.push(nodeToRef(node));
        break;
    }
  }
}


// ─── Utility: Generate analysis ID ──────────────────────────────────────

function generateAnalysisId(): string {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 10);
  return `impact_${ts}_${rand}`;
}

// ─── Core: Policy Loader ────────────────────────────────────────────────

/**
 * Load a policy document from DB by policyId.
 */
async function loadPolicyFromDb(policyId: string): Promise<PolicyDocument | null> {
  try {
    const record = await db.declPolicy.findUnique({
      where: { policyId },
    });

    if (!record) return null;

    return {
      apiVersion: record.apiVersion,
      kind: "PolicyDocument",
      metadata: {
        id: record.policyId,
        name: record.name,
        version: record.version,
        description: record.description,
        compliance: JSON.parse(record.compliance),
        labels: JSON.parse(record.labels),
        author: record.author ?? undefined,
        createdAt: record.createdAt.toISOString(),
        updatedAt: record.updatedAt.toISOString(),
      },
      statements: JSON.parse(record.statements),
      tests: JSON.parse(record.tests),
    };
  } catch (error) {
    console.error(`[ImpactAnalysis] Failed to load policy ${policyId}:`, error);
    return null;
  }
}

// ─── Core: Direct Dependency Finder ─────────────────────────────────────

/**
 * Find PolicySets that reference the given policy.
 */
async function findReferencingPolicySets(policyId: string): Promise<Array<{
  id: string;
  setId: string;
  name: string;
  policies: string;
  entry: PolicySetEntry;
}>> {
  const results: Array<{
    id: string;
    setId: string;
    name: string;
    policies: string;
    entry: PolicySetEntry;
  }> = [];

  try {
    const policySets = await db.policySet.findMany({
      where: { isActive: true },
    });

    for (const ps of policySets) {
      const entries: PolicySetEntry[] = JSON.parse(ps.policies);
      const matchingEntry = entries.find((e) => e.policyId === policyId);
      if (matchingEntry) {
        results.push({
          id: ps.id,
          setId: ps.setId,
          name: ps.name,
          policies: ps.policies,
          entry: matchingEntry,
        });
      }
    }
  } catch (error) {
    console.error("[ImpactAnalysis] Failed to find referencing policy sets:", error);
  }

  return results;
}

/**
 * Find Playbooks that activate the given policy.
 */
async function findReferencingPlaybooks(policyId: string): Promise<Array<{
  playbookId: string;
  name: string;
  industry: string;
  policies: string;
  subIndustry: string | null;
}>> {
  const results: Array<{
    playbookId: string;
    name: string;
    industry: string;
    policies: string;
    subIndustry: string | null;
  }> = [];

  try {
    const playbooks = await db.playbook.findMany({
      where: { isActive: true },
    });

    for (const pb of playbooks) {
      const policyRefs = JSON.parse(pb.policies) as Array<{ policyId: string; role?: string }>;
      if (policyRefs.some((ref) => ref.policyId === policyId)) {
        results.push({
          playbookId: pb.playbookId,
          name: pb.name,
          industry: pb.industry,
          policies: pb.policies,
          subIndustry: pb.subIndustry,
        });
      }
    }
  } catch (error) {
    console.error("[ImpactAnalysis] Failed to find referencing playbooks:", error);
  }

  return results;
}

/**
 * Find tools protected by this policy (via AccessPolicy/ToolAccessPolicy links).
 */
async function findProtectedTools(policyId: string): Promise<Array<{
  toolId: string;
  toolName: string;
  riskLevel: string;
  accessPolicyId: string;
  accessPolicyName: string;
  accessPolicyEffect: string;
}>> {
  const results: Array<{
    toolId: string;
    toolName: string;
    riskLevel: string;
    accessPolicyId: string;
    accessPolicyName: string;
    accessPolicyEffect: string;
  }> = [];

  try {
    // AccessPolicy names may contain policyId reference — we search by name pattern
    // and also check if the policyId appears in conditions JSON
    const accessPolicies = await db.accessPolicy.findMany();

    for (const ap of accessPolicies) {
      // Check if this access policy references our policy
      const referencesPolicy =
        ap.name.includes(policyId) ||
        ap.conditions.includes(policyId) ||
        ap.description.includes(policyId);

      if (!referencesPolicy) continue;

      // Find tools linked to this access policy
      const toolLinks = await db.toolAccessPolicy.findMany({
        where: { policyId: ap.id },
        include: { tool: true },
      });

      for (const link of toolLinks) {
        results.push({
          toolId: link.tool.id,
          toolName: link.tool.name,
          riskLevel: link.tool.riskLevel,
          accessPolicyId: ap.id,
          accessPolicyName: ap.name,
          accessPolicyEffect: ap.effect,
        });
      }
    }

    // Also find tools that have the policyId in their metadata or that are
    // referenced in DeclPolicy statements matching tool categories
    const declPolicy = await db.declPolicy.findUnique({
      where: { policyId },
    });

    if (declPolicy) {
      const statements = JSON.parse(declPolicy.statements) as Array<{
        resource: string;
        action: string;
        effect: string;
      }>;

      // Find tools whose names match policy resource patterns
      const allTools = await db.mcpTool.findMany({
        where: { status: "active" },
      });

      for (const tool of allTools) {
        // Skip if already found
        if (results.some((r) => r.toolId === tool.id)) continue;

        // Check if any statement resource pattern matches this tool
        const matchesTool = statements.some((stmt) => {
          const resource = stmt.resource;
          if (resource === "*") return true;
          if (resource === tool.name) return true;
          if (resource.endsWith("/*") && tool.name.startsWith(resource.slice(0, -2))) return true;
          if (resource.includes(tool.category)) return true;
          return false;
        });

        if (matchesTool) {
          results.push({
            toolId: tool.id,
            toolName: tool.name,
            riskLevel: tool.riskLevel,
            accessPolicyId: "",
            accessPolicyName: "(policy-statement)",
            accessPolicyEffect: statements.find((s) => {
              const resource = s.resource;
              return resource === "*" || resource === tool.name ||
                (resource.endsWith("/*") && tool.name.startsWith(resource.slice(0, -2))) ||
                resource.includes(tool.category);
            })?.effect ?? "deny",
          });
        }
      }
    }
  } catch (error) {
    console.error("[ImpactAnalysis] Failed to find protected tools:", error);
  }

  return results;
}

/**
 * Find approval requests targeting this policy.
 */
async function findReferencingApprovals(policyId: string): Promise<Array<{
  approvalId: string;
  title: string;
  status: string;
  priority: string;
  requestedBy: string;
}>> {
  const results: Array<{
    approvalId: string;
    title: string;
    status: string;
    priority: string;
    requestedBy: string;
  }> = [];

  try {
    const approvals = await db.policyApproval.findMany({
      where: { targetPolicyId: policyId },
    });

    for (const a of approvals) {
      results.push({
        approvalId: a.approvalId,
        title: a.title,
        status: a.status,
        priority: a.priority,
        requestedBy: a.requestedBy,
      });
    }
  } catch (error) {
    console.error("[ImpactAnalysis] Failed to find referencing approvals:", error);
  }

  return results;
}

// ─── Core: Indirect Dependency Finder ───────────────────────────────────

/**
 * Find policies composed with the target in the same PolicySets.
 */
async function findComposedPolicies(
  policySetIds: string[],
  excludePolicyId: string,
): Promise<DependencyNode[]> {
  const nodes: DependencyNode[] = [];

  try {
    for (const setId of policySetIds) {
      const ps = await db.policySet.findUnique({
        where: { setId },
      });

      if (!ps) continue;

      const entries: PolicySetEntry[] = JSON.parse(ps.policies);
      for (const entry of entries) {
        if (entry.policyId === excludePolicyId) continue;

        // Check if the referenced policy exists
        const exists = await db.declPolicy.findUnique({
          where: { policyId: entry.policyId },
        });

        if (exists) {
          nodes.push({
            id: entry.policyId,
            type: "policy",
            name: exists.name,
            dependencyType: DependencyTypeValues.COMPOSED_BY,
            hardDependency: entry.required,
            children: [],
            data: {
              policyId: entry.policyId,
              version: entry.version,
              priority: entry.priority,
              required: entry.required,
              setName: ps.name,
            },
          });
        }
      }
    }
  } catch (error) {
    console.error("[ImpactAnalysis] Failed to find composed policies:", error);
  }

  return nodes;
}

/**
 * Find other policies referenced by affected playbooks.
 */
async function findPlaybookSiblingPolicies(
  playbookIds: string[],
  excludePolicyId: string,
): Promise<DependencyNode[]> {
  const nodes: DependencyNode[] = [];
  const seen = new Set<string>();

  try {
    for (const playbookId of playbookIds) {
      const pb = await db.playbook.findUnique({
        where: { playbookId },
      });

      if (!pb) continue;

      const policyRefs = JSON.parse(pb.policies) as Array<{ policyId: string; role?: string }>;
      for (const ref of policyRefs) {
        if (ref.policyId === excludePolicyId) continue;
        if (seen.has(ref.policyId)) continue;
        seen.add(ref.policyId);

        const exists = await db.declPolicy.findUnique({
          where: { policyId: ref.policyId },
        });

        if (exists) {
          nodes.push({
            id: ref.policyId,
            type: "policy",
            name: exists.name,
            dependencyType: DependencyTypeValues.ACTIVATED_BY,
            hardDependency: false,
            children: [],
            data: {
              policyId: ref.policyId,
              role: ref.role ?? "unknown",
              playbookName: pb.name,
            },
          });
        }
      }
    }
  } catch (error) {
    console.error("[ImpactAnalysis] Failed to find playbook sibling policies:", error);
  }

  return nodes;
}

// ─── Core: Downstream Change Prediction ────────────────────────────────

/**
 * Predict downstream evaluation changes for affected tools.
 * Compares current verdict vs proposed verdict.
 */
async function predictDownstreamChanges(
  currentDocument: PolicyDocument,
  proposedDocument: PolicyDocument | undefined,
  affectedTools: AffectedToolRef[],
  depth: ImpactAnalysisDepth,
): Promise<DownstreamChange[]> {
  const changes: DownstreamChange[] = [];

  if (!proposedDocument) {
    // Without a proposed document, we can only estimate based on policy removal
    for (const tool of affectedTools) {
      changes.push({
        request: `tool:${tool.toolId}`,
        currentEffect: tool.currentVerdict,
        predictedEffect: "deny" as PolicyEffectV2, // removal defaults to deny
        confidence: 0.6,
        reason: "Policy change may remove current access — deny-by-default fallback",
      });
    }
    return changes;
  }

  // For each affected tool, compare current vs proposed verdict
  for (const tool of affectedTools) {
    const currentVerdict = tool.currentVerdict;

    // Simulate proposed document evaluation for this tool
    const proposedVerdict = simulateVerdict(proposedDocument, tool.name, "execute");

    if (currentVerdict !== proposedVerdict) {
      changes.push({
        request: `tool:${tool.toolId}`,
        currentEffect: currentVerdict,
        predictedEffect: proposedVerdict,
        confidence: depth === ImpactAnalysisDepthValues.DEEP ? 0.9 :
                    depth === ImpactAnalysisDepthValues.STANDARD ? 0.75 : 0.6,
        reason: buildChangeReason(currentVerdict, proposedVerdict, tool.name),
      });
    }
  }

  return changes;
}

/**
 * Simple verdict simulation based on document statement matching.
 */
function simulateVerdict(
  document: PolicyDocument,
  resourceName: string,
  actionName: string,
): PolicyEffectV2 {
  const matchedStatements = document.statements.filter((stmt) => {
    const resourceMatch = stmt.resource === "*" ||
      stmt.resource === resourceName ||
      (stmt.resource.endsWith("/*") && resourceName.startsWith(stmt.resource.slice(0, -2)));

    const actionMatch = stmt.action === "*" ||
      stmt.action === actionName;

    return resourceMatch && actionMatch;
  });

  if (matchedStatements.length === 0) {
    return "deny"; // deny-by-default
  }

  // Sort by priority (highest first), deny wins on tie
  matchedStatements.sort((a, b) => {
    if (b.priority !== a.priority) return b.priority - a.priority;
    const effectOrder: Record<string, number> = { deny: 0, conditional: 1, allow: 2 };
    return (effectOrder[a.effect] ?? 3) - (effectOrder[b.effect] ?? 3);
  });

  return matchedStatements[0]!.effect as PolicyEffectV2;
}

/**
 * Build a human-readable reason for a verdict change.
 */
function buildChangeReason(
  from: PolicyEffectV2,
  to: PolicyEffectV2,
  toolName: string,
): string {
  if (from === "allow" && to === "deny") {
    return `Tool "${toolName}" will be BLOCKED — access changes from ALLOW to DENY`;
  }
  if (from === "deny" && to === "allow") {
    return `Tool "${toolName}" will be OPENED — access changes from DENY to ALLOW`;
  }
  if (from === "allow" && to === "conditional") {
    return `Tool "${toolName}" will require CONDITIONAL approval instead of ALLOW`;
  }
  if (from === "deny" && to === "conditional") {
    return `Tool "${toolName}" will become CONDITIONAL instead of DENY`;
  }
  if (from === "conditional" && to === "deny") {
    return `Tool "${toolName}" will be BLOCKED — conditional access removed, now DENY`;
  }
  if (from === "conditional" && to === "allow") {
    return `Tool "${toolName}" will be fully ALLOWED — conditional restriction removed`;
  }
  return `Tool "${toolName}" verdict changes from ${from} to ${to}`;
}

// ─── Core: Blast Radius Calculation ────────────────────────────────────

/**
 * Calculate blast radius from analysis components.
 *
 * Risk score formula:
 *   - 10 points per direct dependency
 *   - 5 points per indirect dependency
 *   - 20 points per tool that changes from ALLOW → DENY
 *   - 15 points per tool that changes from DENY → ALLOW
 *   - 10 points per playbook with compliance score change
 *   - Cap at 100
 *
 * Risk levels:
 *   - 0-20: LOW
 *   - 21-50: MEDIUM
 *   - 51-80: HIGH
 *   - 81-100: CRITICAL
 *
 * Recovery time: riskScore * 2 minutes
 */
function calculateBlastRadius(
  directDeps: DependencyRef[],
  indirectDeps: DependencyRef[],
  affectedSets: AffectedSetRef[],
  affectedPlaybooks: AffectedPlaybookRef[],
  affectedTools: AffectedToolRef[],
  downstreamChanges: DownstreamChange[],
  complianceStandardsImpacted: number,
): BlastRadius {
  // Risk score components
  let riskScore = 0;

  riskScore += directDeps.length * 10;
  riskScore += indirectDeps.length * 5;

  for (const change of downstreamChanges) {
    if (change.currentEffect === "allow" && change.predictedEffect === "deny") {
      riskScore += 20;
    } else if (change.currentEffect === "deny" && change.predictedEffect === "allow") {
      riskScore += 15;
    }
  }

  // Playbooks with compliance score change
  const playbooksWithComplianceChange = affectedPlaybooks.filter(
    (pb) => pb.complianceScoreChange !== 0,
  );
  riskScore += playbooksWithComplianceChange.length * 10;

  // Cap at 100
  riskScore = Math.min(riskScore, 100);

  // Risk level
  const riskLevel: SimulationRiskLevel =
    riskScore <= 20 ? SimulationRiskLevelValues.LOW :
    riskScore <= 50 ? SimulationRiskLevelValues.MEDIUM :
    riskScore <= 80 ? SimulationRiskLevelValues.HIGH :
    SimulationRiskLevelValues.CRITICAL;

  // Total affected resources
  const resourceIds = new Set<string>();
  for (const d of directDeps) resourceIds.add(`${d.type}:${d.id}`);
  for (const d of indirectDeps) resourceIds.add(`${d.type}:${d.id}`);
  for (const s of affectedSets) resourceIds.add(`policy_set:${s.setId}`);
  for (const p of affectedPlaybooks) resourceIds.add(`playbook:${p.playbookId}`);
  for (const t of affectedTools) resourceIds.add(`tool:${t.toolId}`);

  // Estimated users affected (based on roles linked to tools and playbooks)
  const estimatedUsers = estimateAffectedUsers(affectedTools, affectedPlaybooks);

  // Impact categories
  const categories = buildImpactCategories(
    affectedSets,
    affectedPlaybooks,
    affectedTools,
    downstreamChanges,
    complianceStandardsImpacted,
    estimatedUsers,
  );

  return {
    totalAffectedResources: resourceIds.size,
    totalAffectedUsers: estimatedUsers,
    riskScore,
    riskLevel,
    estimatedRecoveryMinutes: riskScore * 2,
    categories,
  };
}

/**
 * Estimate the number of affected users based on tool risk levels and playbook activations.
 */
function estimateAffectedUsers(
  tools: AffectedToolRef[],
  playbooks: AffectedPlaybookRef[],
): number {
  let users = 0;

  // Estimate users per tool by risk level
  for (const tool of tools) {
    switch (tool.riskLevel) {
      case "critical": users += 50; break;
      case "high": users += 30; break;
      case "medium": users += 15; break;
      default: users += 5; break;
    }
  }

  // Estimate users per playbook activation (industry-based)
  for (const pb of playbooks) {
    users += 20; // baseline per playbook
  }

  return users;
}

/**
 * Build impact categories for the blast radius.
 */
function buildImpactCategories(
  sets: AffectedSetRef[],
  playbooks: AffectedPlaybookRef[],
  tools: AffectedToolRef[],
  changes: DownstreamChange[],
  complianceStandardsImpacted: number,
  estimatedUsers: number,
): ImpactCategory[] {
  const categories: ImpactCategory[] = [];

  // Policy Sets
  if (sets.length > 0) {
    const maxPriority = Math.max(...sets.map((s) => s.priority), 0);
    categories.push({
      name: "Policy Sets",
      affectedCount: sets.length,
      severity: maxPriority >= 100 ? ConflictSeverityValues.CRITICAL :
                maxPriority >= 50 ? ConflictSeverityValues.HIGH :
                ConflictSeverityValues.MEDIUM,
      description: `${sets.length} policy set(s) reference the target policy and may need re-composition`,
    });
  }

  // Playbooks
  if (playbooks.length > 0) {
    categories.push({
      name: "Playbooks",
      affectedCount: playbooks.length,
      severity: playbooks.length >= 5 ? ConflictSeverityValues.HIGH :
                playbooks.length >= 2 ? ConflictSeverityValues.MEDIUM :
                ConflictSeverityValues.LOW,
      description: `${playbooks.length} playbook(s) activate this policy across industries`,
    });
  }

  // Tools
  const toolsWithVerdictChange = changes.length;
  if (toolsWithVerdictChange > 0 || tools.length > 0) {
    const allowToDeny = changes.filter(
      (c) => c.currentEffect === "allow" && c.predictedEffect === "deny",
    ).length;
    categories.push({
      name: "Tools",
      affectedCount: toolsWithVerdictChange || tools.length,
      severity: allowToDeny > 0 ? ConflictSeverityValues.CRITICAL :
                toolsWithVerdictChange > 0 ? ConflictSeverityValues.HIGH :
                ConflictSeverityValues.MEDIUM,
      description: `${toolsWithVerdictChange} tool(s) with verdict changes, ${tools.length} total tools protected by this policy`,
    });
  }

  // Compliance
  if (complianceStandardsImpacted > 0) {
    categories.push({
      name: "Compliance",
      affectedCount: complianceStandardsImpacted,
      severity: complianceStandardsImpacted >= 3 ? ConflictSeverityValues.CRITICAL :
                complianceStandardsImpacted >= 2 ? ConflictSeverityValues.HIGH :
                ConflictSeverityValues.MEDIUM,
      description: `${complianceStandardsImpacted} compliance standard(s) may be impacted by this policy change`,
    });
  }

  // Users
  if (estimatedUsers > 0) {
    categories.push({
      name: "Users",
      affectedCount: estimatedUsers,
      severity: estimatedUsers >= 100 ? ConflictSeverityValues.CRITICAL :
                estimatedUsers >= 50 ? ConflictSeverityValues.HIGH :
                estimatedUsers >= 10 ? ConflictSeverityValues.MEDIUM :
                ConflictSeverityValues.LOW,
      description: `Estimated ${estimatedUsers} user(s) affected by access changes`,
    });
  }

  return categories;
}

/**
 * Count compliance standards impacted by this policy.
 */
async function countComplianceStandards(policyId: string): Promise<number> {
  try {
    const policy = await db.declPolicy.findUnique({
      where: { policyId },
    });

    if (!policy) return 0;

    const compliance = JSON.parse(policy.compliance) as Array<{ standard: string }>;
    const standards = new Set(compliance.map((c) => c.standard));

    // Also check if affected playbooks reference additional standards
    const referencingPlaybooks = await findReferencingPlaybooks(policyId);
    for (const pb of referencingPlaybooks) {
      const pbCompliance = JSON.parse(
        (await db.playbook.findUnique({ where: { playbookId: pb.playbookId } }))
          ?.compliance ?? "[]",
      ) as string[];
      for (const std of pbCompliance) {
        standards.add(std);
      }
    }

    return standards.size;
  } catch {
    return 0;
  }
}

// ─── Core: Transitive Closure (DEEP depth) ─────────────────────────────

/**
 * Build full transitive closure of dependencies.
 * Follows indirect references until no new nodes are discovered.
 */
async function buildTransitiveClosure(
  initialIndirectNodes: DependencyNode[],
  visited: Set<string>,
  maxDepth: number,
  currentDepth: number,
): Promise<DependencyNode[]> {
  if (currentDepth >= maxDepth && maxDepth !== -1) return [];
  if (initialIndirectNodes.length === 0) return [];

  const allNewNodes: DependencyNode[] = [];

  for (const node of initialIndirectNodes) {
    if (visited.has(node.id)) continue;
    visited.add(node.id);

    if (node.type === "policy") {
      // Find what references this policy (policy sets, playbooks, tools)
      const policyId = node.id;

      // PolicySets referencing this policy
      const policySets = await findReferencingPolicySets(policyId);
      for (const ps of policySets) {
        const childNode: DependencyNode = {
          id: ps.setId,
          type: "policy_set",
          name: ps.name,
          dependencyType: DependencyTypeValues.COMPOSED_BY,
          hardDependency: ps.entry.required,
          children: [],
        };
        node.children.push(childNode);
        allNewNodes.push(childNode);
      }

      // Playbooks referencing this policy
      const playbooks = await findReferencingPlaybooks(policyId);
      for (const pb of playbooks) {
        const childNode: DependencyNode = {
          id: pb.playbookId,
          type: "playbook",
          name: pb.name,
          dependencyType: DependencyTypeValues.ACTIVATED_BY,
          hardDependency: false,
          children: [],
        };
        node.children.push(childNode);
        allNewNodes.push(childNode);
      }

      // Recurse into children
      const deeper = await buildTransitiveClosure(
        node.children,
        visited,
        maxDepth,
        currentDepth + 1,
      );
      allNewNodes.push(...deeper);
    }
  }

  return allNewNodes;
}

// ─── Main: analyzeImpact ───────────────────────────────────────────────

/**
 * Analyze the impact of changing a policy.
 *
 * Steps:
 *   1. Load the target policy from DB
 *   2. Find direct dependencies (policy sets, playbooks, tools, approvals)
 *   3. Find indirect dependencies (based on analysis depth strategy)
 *   4. Predict downstream evaluation changes
 *   5. Calculate blast radius
 *   6. Persist to DB
 *   7. Return ImpactAnalysisResult
 */
export async function analyzeImpact(
  request: ImpactAnalysisRequest,
): Promise<ImpactAnalysisResult> {
  const { policyId, proposedVersion, proposedDocument, depth, requestedBy } = request;

  // 1. Load target policy
  const currentDocument = await loadPolicyFromDb(policyId);
  if (!currentDocument) {
    throw new Error(`[ImpactAnalysis] Policy "${policyId}" not found`);
  }

  const strategy = DEPTH_STRATEGIES[depth];
  const visitor = new ImpactCollectorVisitor();

  // ── 2. Find direct dependencies ────────────────────────────────────

  // 2a. PolicySets that reference this policy
  const referencingSets = await findReferencingPolicySets(policyId);
  for (const ps of referencingSets) {
    const node: DependencyNode = {
      id: ps.setId,
      type: "policy_set",
      name: ps.name,
      dependencyType: DependencyTypeValues.REFERENCES,
      hardDependency: ps.entry.required,
      children: [],
    };

    const setRef: AffectedSetRef = {
      setId: ps.setId,
      name: ps.name,
      priority: ps.entry.priority,
      needsRecomposition: true,
    };
    node.data = setRef;

    visitor.visitDirect(node);
  }

  // 2b. Playbooks that activate this policy
  const referencingPlaybooks = await findReferencingPlaybooks(policyId);
  for (const pb of referencingPlaybooks) {
    const policyRefs = JSON.parse(pb.policies) as Array<{ policyId: string; role?: string }>;
    const thisRef = policyRefs.find((r) => r.policyId === policyId);

    const node: DependencyNode = {
      id: pb.playbookId,
      type: "playbook",
      name: pb.name,
      dependencyType: DependencyTypeValues.ACTIVATED_BY,
      hardDependency: false,
      children: [],
    };

    const pbRef: AffectedPlaybookRef = {
      playbookId: pb.playbookId,
      name: pb.name,
      industry: pb.industry,
      role: thisRef?.role ?? "unknown",
      complianceScoreChange: 0, // will be updated if strategy includes compliance
    };
    node.data = pbRef;

    visitor.visitDirect(node);
  }

  // 2c. Tools protected by this policy
  const protectedTools = await findProtectedTools(policyId);
  const toolRefsMap = new Map<string, AffectedToolRef>();

  for (const tool of protectedTools) {
    const currentVerdict = (tool.accessPolicyEffect as PolicyEffectV2) || "deny";

    const node: DependencyNode = {
      id: tool.toolId,
      type: "tool",
      name: tool.toolName,
      dependencyType: DependencyTypeValues.PROTECTED_BY,
      hardDependency: true,
      children: [],
    };

    const toolRef: AffectedToolRef = {
      toolId: tool.toolId,
      name: tool.toolName,
      riskLevel: tool.riskLevel,
      currentVerdict,
      predictedVerdict: undefined, // will be set during prediction
    };
    node.data = toolRef;

    // Deduplicate by toolId
    if (!toolRefsMap.has(tool.toolId)) {
      toolRefsMap.set(tool.toolId, toolRef);
      visitor.visitDirect(node);
    }
  }

  // 2d. Approval requests targeting this policy
  const referencingApprovals = await findReferencingApprovals(policyId);
  for (const approval of referencingApprovals) {
    const node: DependencyNode = {
      id: approval.approvalId,
      type: "approval",
      name: approval.title,
      dependencyType: DependencyTypeValues.APPROVED_BY,
      hardDependency: approval.status === "pending_review" || approval.status === "approved",
      children: [],
    };

    visitor.visitDirect(node);
  }

  // ── 3. Find indirect dependencies (based on depth strategy) ──────────

  if (strategy.includeIndirect) {
    // 3a. Policies composed with this one in PolicySets
    const policySetIds = referencingSets.map((ps) => ps.setId);
    const composedPolicies = await findComposedPolicies(policySetIds, policyId);

    for (const cp of composedPolicies) {
      visitor.visitIndirect(cp);
    }

    // 3b. Other policies referenced by affected Playbooks
    const playbookIds = referencingPlaybooks.map((pb) => pb.playbookId);
    const siblingPolicies = await findPlaybookSiblingPolicies(playbookIds, policyId);

    for (const sp of siblingPolicies) {
      visitor.visitIndirect(sp);
    }

    // 3c. For DEEP: full transitive closure
    if (strategy.maxIndirectionLevels === -1) {
      const allIndirectNodes = [...composedPolicies, ...siblingPolicies];
      const visited = new Set<string>([policyId]);
      for (const n of allIndirectNodes) visited.add(n.id);

      await buildTransitiveClosure(
        allIndirectNodes,
        visited,
        -1,
        0,
      );

      // Collect additional indirect nodes from transitive closure
      const collectTransitive = (nodes: DependencyNode[]): void => {
        for (const node of nodes) {
          for (const child of node.children) {
            // Check if already visited
            const existingIndirect = visitor.indirectDeps.find((d) => d.id === child.id);
            if (!existingIndirect) {
              visitor.visitIndirect(child);
            }
            collectTransitive([child]);
          }
        }
      };
      collectTransitive(allIndirectNodes);
    }

    // 3d. For STANDARD (1 level): also find indirect tools from composed policies
    if (depth === ImpactAnalysisDepthValues.STANDARD) {
      for (const cp of composedPolicies) {
        const cpTools = await findProtectedTools(cp.id);
        for (const tool of cpTools) {
          if (toolRefsMap.has(tool.toolId)) continue;

          const node: DependencyNode = {
            id: tool.toolId,
            type: "tool",
            name: tool.toolName,
            dependencyType: DependencyTypeValues.PROTECTED_BY,
            hardDependency: false,
            children: [],
          };

          const toolRef: AffectedToolRef = {
            toolId: tool.toolId,
            name: tool.toolName,
            riskLevel: tool.riskLevel,
            currentVerdict: (tool.accessPolicyEffect as PolicyEffectV2) || "deny",
            predictedVerdict: undefined,
          };
          node.data = toolRef;
          toolRefsMap.set(tool.toolId, toolRef);

          visitor.visitIndirect(node);
        }
      }
    }

    // For DEEP: also find tools for all indirect policy dependencies
    if (depth === ImpactAnalysisDepthValues.DEEP) {
      for (const ind of visitor.indirectDeps) {
        if (ind.type === "policy") {
          const indTools = await findProtectedTools(ind.id);
          for (const tool of indTools) {
            if (toolRefsMap.has(tool.toolId)) continue;

            const node: DependencyNode = {
              id: tool.toolId,
              type: "tool",
              name: tool.toolName,
              dependencyType: DependencyTypeValues.PROTECTED_BY,
              hardDependency: false,
              children: [],
            };

            const toolRef: AffectedToolRef = {
              toolId: tool.toolId,
              name: tool.toolName,
              riskLevel: tool.riskLevel,
              currentVerdict: (tool.accessPolicyEffect as PolicyEffectV2) || "deny",
              predictedVerdict: undefined,
            };
            node.data = toolRef;
            toolRefsMap.set(tool.toolId, toolRef);

            visitor.visitIndirect(node);
          }
        }
      }
    }
  }

  // ── 4. Predict downstream evaluation changes ────────────────────────

  const allAffectedTools = visitor.affectedTools;
  const downstreamChanges = await predictDownstreamChanges(
    currentDocument,
    proposedDocument,
    allAffectedTools,
    depth,
  );

  // Update predicted verdict on affected tools
  for (const change of downstreamChanges) {
    const toolRef = allAffectedTools.find(
      (t) => `tool:${t.toolId}` === change.request,
    );
    if (toolRef) {
      toolRef.predictedVerdict = change.predictedEffect;
    }
  }

  // ── 4b. Update compliance score changes for playbooks ────────────────

  if (strategy.includeComplianceChanges) {
    for (const pbRef of visitor.affectedPlaybooks) {
      // Estimate compliance score change: if policy changes, the playbook's
      // compliance coverage may change. We estimate based on whether the
      // policy is referenced as required.
      const policyRefs = referencingPlaybooks.find(
        (pb) => pb.playbookId === pbRef.playbookId,
      );
      if (policyRefs) {
        const refs = JSON.parse(policyRefs.policies) as Array<{
          policyId: string;
          role?: string;
        }>;
        const thisRef = refs.find((r) => r.policyId === policyId);
        // If this policy is required in the playbook, compliance score may drop
        pbRef.complianceScoreChange = thisRef?.role === "required" ? -10 : -5;
      }
    }
  }

  // ── 5. Calculate blast radius ────────────────────────────────────────

  const directDepRefs = visitor.directDeps.map(nodeToRef);
  const indirectDepRefs = visitor.indirectDeps.map(nodeToRef);

  const complianceStandardsImpacted = await countComplianceStandards(policyId);

  const blastRadius = calculateBlastRadius(
    directDepRefs,
    indirectDepRefs,
    visitor.affectedSets,
    visitor.affectedPlaybooks,
    visitor.affectedTools,
    downstreamChanges,
    complianceStandardsImpacted,
  );

  // ── 6. Build summary ────────────────────────────────────────────────

  const summary = buildSummary(
    policyId,
    depth,
    directDepRefs.length,
    indirectDepRefs.length,
    visitor.affectedSets.length,
    visitor.affectedPlaybooks.length,
    visitor.affectedTools.length,
    downstreamChanges,
    blastRadius,
  );

  // ── 7. Persist to DB ────────────────────────────────────────────────

  const analysisId = generateAnalysisId();

  try {
    await db.policyImpactAnalysis.create({
      data: {
        analysisId,
        policyId,
        proposedVersion: proposedVersion ?? null,
        analysisDepth: depth,
        directDependencies: JSON.stringify(directDepRefs),
        indirectDependencies: JSON.stringify(indirectDepRefs),
        affectedSets: JSON.stringify(visitor.affectedSets),
        affectedPlaybooks: JSON.stringify(visitor.affectedPlaybooks),
        affectedTools: JSON.stringify(visitor.affectedTools),
        blastRadius: JSON.stringify(blastRadius),
        downstreamChanges: JSON.stringify(downstreamChanges),
        requestedBy,
        summary,
      },
    });
  } catch (error) {
    console.error("[ImpactAnalysis] Failed to persist analysis:", error);
    // Continue — return result even if DB write fails
  }

  // ── 8. Return result ────────────────────────────────────────────────

  return {
    policyId,
    analyzedAt: new Date().toISOString(),
    directDependencies: directDepRefs,
    indirectDependencies: indirectDepRefs,
    affectedSets: visitor.affectedSets,
    affectedPlaybooks: visitor.affectedPlaybooks,
    affectedTools: visitor.affectedTools,
    blastRadius,
    downstreamChanges,
    summary,
  };
}

// ─── Summary Builder ───────────────────────────────────────────────────

function buildSummary(
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
