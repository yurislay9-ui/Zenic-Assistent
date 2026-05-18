        `Invalid kind "${set.kind}". Expected "${POLICY_SET_KIND}"`,
      );
    }

    // Validate merge strategy
    if (!VALID_MERGE_STRATEGIES.has(set.defaultMergeStrategy)) {
      throw new Error(
        `Invalid merge strategy "${set.defaultMergeStrategy}". Must be one of: ${[...VALID_MERGE_STRATEGIES].join(", ")}`,
      );
    }

    // Validate metadata
    if (!set.metadata.id || typeof set.metadata.id !== "string") {
      throw new Error("metadata.id is required and must be a string");
    }
    if (!set.metadata.name || typeof set.metadata.name !== "string") {
      throw new Error("metadata.name is required and must be a string");
    }

    // Validate all referenced policy IDs exist
    const policyIds = set.policies.map((e) => e.policyId);
    if (policyIds.length > 0) {
      const existingPolicies = await db.declPolicy.findMany({
        where: {
          policyId: { in: policyIds },
          isActive: true,
        },
        select: { policyId: true },
      });
      const existingIds = new Set(existingPolicies.map((p) => p.policyId));

      const missing = policyIds.filter((id) => !existingIds.has(id));
      if (missing.length > 0) {
        // Check if any missing policies are marked as required
        const missingRequired = set.policies.filter(
          (e) => missing.includes(e.policyId) && e.required,
        );
        if (missingRequired.length > 0) {
          throw new Error(
            `Required policies not found: ${missingRequired.map((e) => e.policyId).join(", ")}`,
          );
        }
      }
    }

    // Check for duplicate setId
    const existing = await db.policySet.findUnique({
      where: { setId: set.metadata.id },
    });
    if (existing) {
      throw new Error(
        `PolicySet with setId "${set.metadata.id}" already exists`,
      );
    }

    // Compute content hash
    const canonicalPayload = {
      apiVersion: set.apiVersion,
      kind: set.kind,
      metadata: set.metadata,
      policies: set.policies,
      defaultMergeStrategy: set.defaultMergeStrategy,
      denyStopsEvaluation: set.denyStopsEvaluation,
    };
    const contentHash = createHash("sha256")
      .update(JSON.stringify(canonicalPayload, Object.keys(canonicalPayload).sort(), 2))
      .digest("hex");

    // Store in DB
    await db.policySet.create({
      data: {
        setId: set.metadata.id,
        name: set.metadata.name,
        description: set.metadata.description,
        apiVersion: set.apiVersion,
        version: set.metadata.version,
        namespace: set.metadata.namespace ?? null,
        labels: JSON.stringify(set.metadata.labels ?? {}),
        policies: JSON.stringify(set.policies),
        defaultMergeStrategy: set.defaultMergeStrategy,
        denyStopsEvaluation: set.denyStopsEvaluation,
        isActive: true,
        contentHash,
        author: set.metadata.author ?? null,
      },
    });

    return set;
  }

  /**
   * Load a policy set from DB by setId.
   */
  async getPolicySet(setId: string): Promise<PolicySet | null> {
    const record = await db.policySet.findUnique({
      where: { setId },
    });

    if (!record) return null;

    return this.mapRecordToPolicySet(record);
  }

  /**
   * List all policy sets, optionally filtered by namespace.
   */
  async listPolicySets(namespace?: string): Promise<PolicySet[]> {
    const where: Record<string, unknown> = { isActive: true };
    if (namespace !== undefined) {
      where.namespace = namespace;
    }

    const records = await db.policySet.findMany({
      where,
      orderBy: { createdAt: "desc" },
    });

    return records.map((r) => this.mapRecordToPolicySet(r));
  }

  /**
   * Compose all policies in a set using the merge strategy.
   * Returns ComposedPolicyResult with merged document, stats, and any conflicts.
   */
  async composePolicySet(setId: string): Promise<ComposedPolicyResult> {
    const startTime = Date.now();

    // Load the policy set
    const policySet = await this.getPolicySet(setId);
    if (!policySet) {
      throw new Error(`PolicySet "${setId}" not found`);
    }

    if (policySet.policies.length === 0) {
      return {
        setId,
        policyCount: 0,
        totalStatements: 0,
        byEffect: { allow: 0, deny: 0, conditional: 0 },
        conflicts: [],
        mergedDocument: buildMergedDocument(
          setId,
          policySet.metadata.name,
          policySet.metadata.description,
          [],
          policySet.metadata.namespace,
        ),
        stats: {
          unionCount: 0,
          intersectionCount: 0,
          overrideCount: 0,
          duplicatesRemoved: 0,
          mergeDuration: Date.now() - startTime,
        },
      };
    }

    // BUG #8 FIX: Batch-load all policies in ONE query instead of N+1 findFirst calls.
    // Before: N queries (one per policy in set). After: 1 query + in-memory version matching.
    const policyDocuments: PolicyDocument[] = [];
    const policyStatementArrays: PolicyStatement[][] = [];

    const allPolicyIds = policySet.policies.map((e) => e.policyId);
    const batchPolicies = await db.declPolicy.findMany({
      where: {
        isActive: true,
        policyId: { in: allPolicyIds },
      },
    });

    // Build lookup: policyId@version → record, and policyId → record (latest)
    const policyLookup = new Map<string, (typeof batchPolicies)[0]>();
    for (const p of batchPolicies) {
      policyLookup.set(p.policyId, p);
      policyLookup.set(`${p.policyId}@${p.version}`, p);
    }

    for (const entry of policySet.policies) {
      const key = entry.version ? `${entry.policyId}@${entry.version}` : entry.policyId;
      let declPolicy = policyLookup.get(key);

      // Fallback: try just policyId (latest version)
      if (!declPolicy && entry.version) {
        declPolicy = policyLookup.get(entry.policyId);
      }

      if (!declPolicy) {
        if (entry.required) {
          throw new Error(
            `Required policy "${entry.policyId}"${entry.version ? ` version "${entry.version}"` : ""} not found in DB`,
          );
        }
        continue;
      }

      const doc: PolicyDocument = {
        apiVersion: declPolicy.apiVersion as typeof import("./types").POLICY_API_VERSION,
        kind: "PolicyDocument",
        metadata: {
          id: declPolicy.policyId,
          name: declPolicy.name,
          version: declPolicy.version,
          description: declPolicy.description,
          compliance: JSON.parse(declPolicy.compliance),
          labels: JSON.parse(declPolicy.labels),
          author: declPolicy.author ?? undefined,
          createdAt: declPolicy.createdAt.toISOString(),
          updatedAt: declPolicy.updatedAt.toISOString(),
        },
        statements: JSON.parse(declPolicy.statements),
        tests: JSON.parse(declPolicy.tests),
      };

      // Apply overrides if specified on the entry
      let finalStatements = doc.statements;
      if (entry.overrides && entry.overrides.length > 0) {
        finalStatements = this.applyOverrides(doc.statements, entry.overrides);
      }

      policyDocuments.push({ ...doc, statements: finalStatements });
      policyStatementArrays.push(finalStatements);
    }

    // Determine the merge strategy (use entry override or set default)
    const mergeStrategy = policySet.defaultMergeStrategy;

    // Apply merge strategy
    let mergedStatements: PolicyStatement[];
    let stats: Partial<CompositionStats>;
    let conflicts: PolicyConflict[] = [];

    switch (mergeStrategy) {
      case "union": {
        const result = mergeUnion(policyStatementArrays);
        mergedStatements = result.statements;
        stats = result.stats;
        break;
      }
      case "intersection": {
        const result = mergeIntersection(policyStatementArrays);
        mergedStatements = result.statements;
        stats = result.stats;
        conflicts = result.conflicts;
        break;
      }
      case "override": {
        const result = mergeOverride(policyStatementArrays);
        mergedStatements = result.statements;
        stats = result.stats;
        break;
