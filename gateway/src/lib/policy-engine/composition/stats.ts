      }
      case "extend": {
        const result = mergeExtend(policyStatementArrays);
        mergedStatements = result.statements;
        stats = result.stats;
        conflicts = result.conflicts;
        break;
      }
      case "priority_merge": {
        const result = mergePriorityMerge(policyStatementArrays);
        mergedStatements = result.statements;
        stats = result.stats;
        conflicts = result.conflicts;
        break;
      }
      default:
        throw new Error(`Unknown merge strategy: ${mergeStrategy}`);
    }

    const mergeDuration = Date.now() - startTime;

    // Compute byEffect counts
    const byEffect: Record<PolicyEffectV2, number> = {
      allow: 0,
      deny: 0,
      conditional: 0,
    };
    for (const stmt of mergedStatements) {
      byEffect[stmt.effect] = (byEffect[stmt.effect] ?? 0) + 1;
    }

    // Build merged document
    const mergedDocument = buildMergedDocument(
      setId,
      policySet.metadata.name,
      policySet.metadata.description,
      mergedStatements,
      policySet.metadata.namespace,
    );

    // Compute content hash of the merged document for integrity tracking
    const mergedContentHash = computeContentHash(mergedDocument);
    mergedDocument.metadata.labels = {
      ...mergedDocument.metadata.labels,
      "zenic.dev/content-hash": mergedContentHash,
    };

    return {
      setId,
      policyCount: policyDocuments.length,
      totalStatements: mergedStatements.length,
      byEffect,
      conflicts,
      mergedDocument,
      stats: {
        unionCount: stats.unionCount ?? 0,
        intersectionCount: stats.intersectionCount ?? 0,
        overrideCount: stats.overrideCount ?? 0,
        duplicatesRemoved: stats.duplicatesRemoved ?? 0,
        mergeDuration,
      },
    };
  }

  /**
   * Add a policy entry to an existing set.
   */
  async addPolicyToSet(setId: string, entry: PolicySetEntry): Promise<PolicySet> {
    // Validate the policy exists
    const policyExists = await db.declPolicy.findFirst({
      where: {
        policyId: entry.policyId,
        isActive: true,
        ...(entry.version ? { version: entry.version } : {}),
      },
    });

    if (!policyExists && entry.required) {
      throw new Error(
        `Required policy "${entry.policyId}"${entry.version ? ` version "${entry.version}"` : ""} not found`,
      );
    }

    // Load current set
    const current = await db.policySet.findUnique({
      where: { setId },
    });

    if (!current) {
      throw new Error(`PolicySet "${setId}" not found`);
    }

    // Parse current policies
    const policies: PolicySetEntry[] = JSON.parse(current.policies);

    // Check for duplicate entry
    const alreadyExists = policies.some(
      (p) => p.policyId === entry.policyId && p.version === entry.version,
    );
    if (alreadyExists) {
      throw new Error(
        `Policy "${entry.policyId}"${entry.version ? ` version "${entry.version}"` : ""} already in set "${setId}"`,
      );
    }

    // Add the new entry
    policies.push(entry);

    // Recompute content hash
    const setObj = this.mapRecordToPolicySet({ ...current, policies: JSON.stringify(policies) });
    const contentHash = this.computeSetContentHash(setObj);

    // Update in DB
    await db.policySet.update({
      where: { setId },
      data: {
        policies: JSON.stringify(policies),
        contentHash,
      },
    });

    return setObj;
  }

  /**
   * Remove a policy entry from a set.
   */
  async removePolicyFromSet(setId: string, policyId: string): Promise<PolicySet> {
    // Load current set
    const current = await db.policySet.findUnique({
      where: { setId },
    });

    if (!current) {
      throw new Error(`PolicySet "${setId}" not found`);
    }

    // Parse and filter
    const policies: PolicySetEntry[] = JSON.parse(current.policies);
    const filtered = policies.filter((p) => p.policyId !== policyId);

    if (filtered.length === policies.length) {
      throw new Error(
        `Policy "${policyId}" not found in set "${setId}"`,
      );
    }

    // Recompute content hash
    const setObj = this.mapRecordToPolicySet({ ...current, policies: JSON.stringify(filtered) });
    const contentHash = this.computeSetContentHash(setObj);

    // Update in DB
    await db.policySet.update({
      where: { setId },
      data: {
        policies: JSON.stringify(filtered),
        contentHash,
      },
    });

    return setObj;
  }

  /**
   * Delete a policy set.
   */
  async deletePolicySet(setId: string): Promise<void> {
    const existing = await db.policySet.findUnique({
      where: { setId },
    });

    if (!existing) {
      throw new Error(`PolicySet "${setId}" not found`);
    }

    await db.policySet.delete({
      where: { setId },
    });
  }

  // ─── Internal Helpers ──────────────────────────────────────────────────

  /**
   * Map a DB record to a PolicySet type.
   */
  private mapRecordToPolicySet(record: {
    setId: string;
    name: string;
    description: string;
    apiVersion: string;
    version: string;
    namespace: string | null;
    labels: string;
    policies: string;
    defaultMergeStrategy: string;
    denyStopsEvaluation: boolean;
    isActive: boolean;
    contentHash: string;
    author: string | null;
    createdAt: Date;
    updatedAt: Date;
  }): PolicySet {
    return {
      apiVersion: record.apiVersion as typeof POLICY_SET_API_VERSION,
      kind: POLICY_SET_KIND,
      metadata: {
        id: record.setId,
        name: record.name,
        version: record.version,
        description: record.description,
        namespace: record.namespace ?? undefined,
        labels: JSON.parse(record.labels),
        author: record.author ?? undefined,
        createdAt: record.createdAt.toISOString(),
        updatedAt: record.updatedAt.toISOString(),
      },
      policies: JSON.parse(record.policies),
      defaultMergeStrategy: record.defaultMergeStrategy as MergeStrategy,
      denyStopsEvaluation: record.denyStopsEvaluation,
    };
  }

  /**
   * Compute content hash for a PolicySet.
   */
  private computeSetContentHash(set: PolicySet): string {
    const canonicalPayload = {
      apiVersion: set.apiVersion,
      kind: set.kind,
      metadata: set.metadata,
      policies: set.policies,
      defaultMergeStrategy: set.defaultMergeStrategy,
      denyStopsEvaluation: set.denyStopsEvaluation,
    };
    return createHash("sha256")
      .update(JSON.stringify(canonicalPayload, Object.keys(canonicalPayload).sort(), 2))
      .digest("hex");
  }

  /**
   * Apply partial overrides to statements.
   */
  private applyOverrides(
    statements: PolicyStatement[],
    overrides: Partial<PolicyStatement>[],
  ): PolicyStatement[] {
    const result = statements.map((stmt) => {
      const matchingOverride = overrides.find((o) => o.id === stmt.id);
      if (matchingOverride) {
        return { ...stmt, ...matchingOverride } as PolicyStatement;
      }
      return stmt;
    });

    // Add new statements from overrides that don't match existing IDs
    const existingIds = new Set(statements.map((s) => s.id));
    for (const override of overrides) {
      if (override.id && !existingIds.has(override.id)) {
        result.push(override as PolicyStatement);
      }
    }

    return result;
  }
}

// ─── Singleton ────────────────────────────────────────────────────────

let engineInstance: CompositionEngine | null = null;

/**
 * Get the singleton CompositionEngine instance.
 */
export function getCompositionEngine(): CompositionEngine {
  if (!engineInstance) {
    engineInstance = new CompositionEngine();
  }
  return engineInstance;
}

/**
 * Reset the singleton CompositionEngine instance.
 */
export function resetCompositionEngine(): void {
  engineInstance = null;
}
