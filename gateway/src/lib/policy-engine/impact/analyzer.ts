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
