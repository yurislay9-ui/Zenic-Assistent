    // 1. EFFECT_CONTRADICTION: same resource/action overlap, different effects
    if (stmtA.effect !== stmtB.effect) {
      conflicts.push(this.makeConflict(
        ConflictType.EFFECT_CONTRADICTION,
        refA, refB,
      ));

      // Also check PRIORITY_COLLISION if same priority
      if (stmtA.priority === stmtB.priority) {
        conflicts.push(this.makeConflict(
          ConflictType.PRIORITY_COLLISION,
          refA, refB,
        ));
      }
    } else {
      // Same effect — check for other conflict types

      // 2. PRIORITY_COLLISION: same priority, same effect but overlapping scope
      if (stmtA.priority === stmtB.priority && stmtA.effect === stmtB.effect) {
        // Same effect and priority isn't necessarily a conflict,
        // but overlapping conditions make it ambiguous
        const condRelation = analyzeConditionOverlap(stmtA.conditions, stmtB.conditions);
        if (condRelation !== "disjoint") {
          conflicts.push(this.makeConflict(
            ConflictType.PRIORITY_COLLISION,
            refA, refB,
          ));
        }
      }
    }

    // 3. CONDITION_OVERLAP: overlapping condition scopes
    const condRelation = analyzeConditionOverlap(stmtA.conditions, stmtB.conditions);
    if (condRelation === "overlap" || condRelation === "a_subset_b" || condRelation === "b_subset_a") {
      // Only report condition overlap if not already captured by other types
      const isAlreadyCovered = conflicts.some(
        (c) => c.type === ConflictType.EFFECT_CONTRADICTION || c.type === ConflictType.PRIORITY_COLLISION,
      );
      if (!isAlreadyCovered) {
        conflicts.push(this.makeConflict(
          ConflictType.CONDITION_OVERLAP,
          refA, refB,
        ));
      }
    }

    // 4. REDUNDANT_RULE: one statement is a subset of another
    if (isStatementContainedBy(stmtB, stmtA)) {
      conflicts.push(this.makeConflict(
        ConflictType.REDUNDANT_RULE,
        refA, refB,
      ));
    } else if (isStatementContainedBy(stmtA, stmtB)) {
      conflicts.push(this.makeConflict(
        ConflictType.REDUNDANT_RULE,
        refB, refA,
      ));
    }

    // 5. SHADOW_RULE: higher-priority statement shadows lower-priority
    if (doesStatementShadow(stmtA, stmtB)) {
      conflicts.push(this.makeConflict(
        ConflictType.SHADOW_RULE,
        refA, refB,
      ));
    } else if (doesStatementShadow(stmtB, stmtA)) {
      conflicts.push(this.makeConflict(
        ConflictType.SHADOW_RULE,
        refB, refA,
      ));
    }

    // 6. SCOPE_CONFLICT: policies from different namespaces with overlapping scope
    if (a.namespace && b.namespace && a.namespace !== b.namespace) {
      conflicts.push(this.makeConflict(
        ConflictType.SCOPE_CONFLICT,
        refA, refB,
      ));
    }

    return conflicts;
  }

  /**
   * Create a PolicyConflict object.
   */
  private makeConflict(
    type: ConflictTypeType,
    refA: ConflictStatementRef,
    refB: ConflictStatementRef,
  ): PolicyConflict {
    const severity = scoreSeverity(type, refA.effect, refB.effect);
    const suggestedResolution = suggestResolution(type);

    return {
      id: this.generateConflictId(type, refA, refB),
      type,
      severity,
      statementA: refA,
      statementB: refB,
      description: generateDescription(type, refA, refB),
      suggestedResolution,
      resolved: false,
    };
  }

  /**
   * Generate a unique conflict ID.
   */
  private generateConflictId(
    type: ConflictTypeType,
    refA: ConflictStatementRef,
    refB: ConflictStatementRef,
  ): string {
    // Deterministic ID based on conflict content
    const raw = `${type}:${refA.policyId}:${refA.statementId}:${refB.policyId}:${refB.statementId}`;
    const hash = computeContentHash({
      apiVersion: "policy.zenic.dev/v1",
      kind: "PolicyDocument",
      metadata: { id: raw, name: "conflict", version: "1.0.0", description: "" },
      statements: [],
    });
    return `conflict_${hash.slice(0, 16)}`;
  }

  /**
   * Generate a deduplication key for a conflict.
   */
  private conflictKey(conflict: PolicyConflict): string {
    // Normalize ordering so A↔B and B↔A produce the same key
    const ids = [conflict.statementA.policyId + ":" + conflict.statementA.statementId,
      conflict.statementB.policyId + ":" + conflict.statementB.statementId].sort();
    return `${conflict.type}:${ids[0]}:${ids[1]}`;
  }

  // ─── Private: DB Operations ───────────────────────────────────────

  /**
   * Clear old conflict records for the analyzed policies.
   */
  private async clearOldConflicts(policyIds?: string[]): Promise<void> {
    if (policyIds && policyIds.length > 0) {
      await db.policyConflictRecord.deleteMany({
        where: {
          OR: [
            { policyIdA: { in: policyIds } },
            { policyIdB: { in: policyIds } },
          ],
        },
      });
    } else {
      // Clear all conflict records on full scan
      await db.policyConflictRecord.deleteMany({});
    }
  }

  /**
   * Persist detected conflicts to the PolicyConflictRecord table.
   */
  private async persistConflicts(conflicts: PolicyConflict[]): Promise<void> {
    if (conflicts.length === 0) return;

    // Batch insert using createMany for efficiency
    const records = conflicts.map((c) => ({
      conflictId: c.id,
      type: c.type,
      severity: c.severity,
      policyIdA: c.statementA.policyId,
      versionA: c.statementA.version,
      statementIdA: c.statementA.statementId,
      effectA: c.statementA.effect,
      resourceA: c.statementA.resource,
      actionA: c.statementA.action,
      policyIdB: c.statementB.policyId,
      versionB: c.statementB.version,
      statementIdB: c.statementB.statementId,
      effectB: c.statementB.effect,
      resourceB: c.statementB.resource,
      actionB: c.statementB.action,
      description: c.description,
      suggestedResolution: c.suggestedResolution,
      resolved: c.resolved,
    }));

    // Insert in chunks to avoid SQLite limits
    const CHUNK_SIZE = 50;
    for (let i = 0; i < records.length; i += CHUNK_SIZE) {
      const chunk = records.slice(i, i + CHUNK_SIZE);
      await db.policyConflictRecord.createMany({ data: chunk, skipDuplicates: true });
    }
  }

  /**
   * Convert a DB record to a PolicyConflict object.
   */
  private recordToConflict(
    record: Awaited<ReturnType<typeof db.policyConflictRecord.findFirst>> & {
      resolvedAt?: Date | null;
    },
  ): PolicyConflict {
    const refA: ConflictStatementRef = {
      policyId: record.policyIdA,
      version: record.versionA ?? "unknown",
      statementId: record.statementIdA,
      effect: record.effectA as PolicyEffectV2,
      resource: record.resourceA,
      action: record.actionA,
    };

    const refB: ConflictStatementRef = {
      policyId: record.policyIdB,
      version: record.versionB ?? "unknown",
      statementId: record.statementIdB,
      effect: record.effectB as PolicyEffectV2,
      resource: record.resourceB,
      action: record.actionB,
    };

    let resolution: ConflictResolution | undefined;
    if (record.resolved && record.resolutionStrategy) {
      resolution = {
        strategy: record.resolutionStrategy as ConflictResolutionStrategyType,
        resolvedBy: record.resolvedBy ?? "unknown",
        resolvedAt: record.resolvedAt ? new Date(record.resolvedAt).toISOString() : new Date().toISOString(),
        note: record.resolutionNote ?? "",
      };
    }

    return {
      id: record.conflictId,
      type: record.type as ConflictTypeType,
      severity: record.severity as ConflictSeverityType,
      statementA: refA,
      statementB: refB,
      description: record.description,
      suggestedResolution: record.suggestedResolution as ConflictResolutionStrategyType,
      resolved: record.resolved,
      resolution,
    };
  }

  // ─── Private: Resolution Strategy Selection ───────────────────────

  /**
   * Determine the effective resolution strategy for a conflict
   * during auto-resolution.
   */
  private resolveStrategyForConflict(
    record: { type: string; suggestedResolution: string },
    defaultStrategy: ConflictResolutionStrategyType,
  ): ConflictResolutionStrategyType {
    // For effect contradictions, always use deny_wins unless overridden
    if (record.type === ConflictType.EFFECT_CONTRADICTION && defaultStrategy === ConflictResolutionStrategy.DENY_WINS) {
      return ConflictResolutionStrategy.DENY_WINS;
    }

    // For scope conflicts, always require manual resolution
    if (record.type === ConflictType.SCOPE_CONFLICT) {
      return ConflictResolutionStrategy.MANUAL;
    }

    return defaultStrategy;
  }

  // ─── Private: Report Building ─────────────────────────────────────

  /**
   * Build a ConflictReport from detected conflicts.
   */
  private buildReport(
    conflicts: PolicyConflict[],
    statements: LoadedStatement[],
    startTime: number,
  ): ConflictReport {
    const uniquePolicies = new Set(statements.map((s) => s.policyId));
    const bySeverity = this.emptyBySeverity();
    const byType = this.emptyByType();

    for (const c of conflicts) {
      bySeverity[c.severity] = (bySeverity[c.severity] ?? 0) + 1;
      byType[c.type] = (byType[c.type] ?? 0) + 1;
    }

    const conflictScore = this.computeConflictScore(conflicts);
    const summary = this.formatSummary(conflicts.length, conflictScore, uniquePolicies.size);

    return {
      generatedAt: new Date().toISOString(),
      totalPolicies: uniquePolicies.size,
      totalConflicts: conflicts.length,
      bySeverity,
      byType,
      conflicts,
      conflictScore,
      summary,
    };
  }

  /**
   * Compute the conflict score (0-100, lower is better).
   * Weighted by severity: CRITICAL=25, HIGH=15, MEDIUM=8, LOW=3, INFO=1
   * Capped at 100.
   */
  private computeConflictScore(conflicts: PolicyConflict[]): number {
    const WEIGHTS: Record<ConflictSeverityType, number> = {
      [ConflictSeverity.CRITICAL]: 25,
      [ConflictSeverity.HIGH]: 15,
      [ConflictSeverity.MEDIUM]: 8,
      [ConflictSeverity.LOW]: 3,
      [ConflictSeverity.INFO]: 1,
    };

    let score = 0;
    for (const c of conflicts) {
      // Unresolved conflicts count fully; resolved ones count 20%
      const weight = c.resolved ? WEIGHTS[c.severity] * 0.2 : WEIGHTS[c.severity];
      score += weight;
    }

    return Math.min(100, Math.round(score));
  }

  /**
   * Format a summary string for the conflict report.
   */
  private formatSummary(totalConflicts: number, conflictScore: number, totalPolicies: number): string {
    if (totalConflicts === 0) {
      return `No conflicts detected across ${totalPolicies} active policies. Conflict score: 0 (excellent).`;
    }

    let grade: string;
    if (conflictScore <= 10) grade = "good";
    else if (conflictScore <= 30) grade = "fair";
    else if (conflictScore <= 60) grade = "poor";
    else grade = "critical";

    return `Detected ${totalConflicts} conflict${totalConflicts !== 1 ? "s" : ""} across ` +
      `${totalPolicies} active policies. Conflict score: ${conflictScore}/100 (${grade}). ` +
      `Review and resolve critical conflicts first.`;
  }

  /**
   * Create an empty by-severity map.
   */
  private emptyBySeverity(): Record<ConflictSeverityType, number> {
    return {
      [ConflictSeverity.CRITICAL]: 0,
      [ConflictSeverity.HIGH]: 0,
      [ConflictSeverity.MEDIUM]: 0,
      [ConflictSeverity.LOW]: 0,
      [ConflictSeverity.INFO]: 0,
    };
  }

  /**
   * Create an empty by-type map.
   */
  private emptyByType(): Record<ConflictTypeType, number> {
    return {
      [ConflictType.EFFECT_CONTRADICTION]: 0,
      [ConflictType.PRIORITY_COLLISION]: 0,
      [ConflictType.CONDITION_OVERLAP]: 0,
      [ConflictType.REDUNDANT_RULE]: 0,
      [ConflictType.SHADOW_RULE]: 0,
      [ConflictType.SCOPE_CONFLICT]: 0,
    };
  }

  /**
   * Clear the internal cache.
   */
  clearCache(): void {
    this.cache.clear();
  }
}

// ─── Singleton ────────────────────────────────────────────────────────

let detectorInstance: ConflictDetector | null = null;

/**
 * Get the singleton ConflictDetector instance.
 */
export function getConflictDetector(): ConflictDetector {
  if (!detectorInstance) {
    detectorInstance = new ConflictDetector();
  }
  return detectorInstance;
}

/**
 * Reset the singleton ConflictDetector instance.
 */
export function resetConflictDetector(): void {
  if (detectorInstance) {
    detectorInstance.clearCache();
  }
  detectorInstance = null;
}
