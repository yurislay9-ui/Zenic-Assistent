        `from different namespaces have overlapping scope`;

    default:
      return `Unknown conflict between "${refA.statementId}" and "${refB.statementId}"`;
  }
}

// ─── Loaded Policy Statement (internal) ───────────────────────────────

interface LoadedStatement {
  policyId: string;
  version: string;
  statement: PolicyStatement;
  namespace?: string;
}

// ─── Conflict Detector Options ────────────────────────────────────────

export interface ConflictDetectionOptions {
  /** Filter by severity */
  severity?: ConflictSeverityType;
  /** Filter by conflict type */
  type?: ConflictTypeType;
  /** Filter by resolved status */
  resolved?: boolean;
  /** Filter by policy ID (checks both policyIdA and policyIdB) */
  policyId?: string;
  /** Maximum number of results */
  limit?: number;
  /** Offset for pagination */
  offset?: number;
}

// ─── Conflict Detector Class ──────────────────────────────────────────

export class ConflictDetector {
  private cache: Map<string, PolicyConflict[]> = new Map();

  /**
   * Detect conflicts across all active policies (or specified ones).
   * Analyzes all statement pairs for conflicts.
   * Persists results to the PolicyConflictRecord DB table.
   */
  async detectConflicts(policies?: string[]): Promise<ConflictReport> {
    const startTime = Date.now();

    // 1. Load policies from DB
    const loadedStatements = await this.loadPolicyStatements(policies);

    if (loadedStatements.length === 0) {
      return {
        generatedAt: new Date().toISOString(),
        totalPolicies: 0,
        totalConflicts: 0,
        bySeverity: this.emptyBySeverity(),
        byType: this.emptyByType(),
        conflicts: [],
        conflictScore: 0,
        summary: "No active policies found — no conflicts to detect.",
      };
    }

    // 2. Clear old conflict records for the analyzed policies
    await this.clearOldConflicts(policies);

    // 3. Analyze all statement pairs
    const conflicts = this.analyzeStatementPairs(loadedStatements);

    // 4. Persist to DB
    await this.persistConflicts(conflicts);

    // 5. Build report
    return this.buildReport(conflicts, loadedStatements, startTime);
  }

  /**
   * Resolve a detected conflict with a chosen strategy.
   */
  async resolveConflict(
    conflictId: string,
    strategy: ConflictResolutionStrategyType,
    resolvedBy: string,
    note: string,
  ): Promise<PolicyConflict | null> {
    const record = await db.policyConflictRecord.findFirst({
      where: { conflictId },
    });

    if (!record) return null;

    const resolution: ConflictResolution = {
      strategy,
      resolvedBy,
      resolvedAt: new Date().toISOString(),
      note,
    };

    await db.policyConflictRecord.update({
      where: { id: record.id },
      data: {
        resolved: true,
        resolutionStrategy: strategy,
        resolvedBy,
        resolutionNote: note,
        resolvedAt: new Date(),
      },
    });

    // Return the updated conflict
    return this.recordToConflict({
      ...record,
      resolved: true,
      resolutionStrategy: strategy,
      resolvedBy,
      resolutionNote: note,
      resolvedAt: new Date(),
    });
  }

  /**
   * Auto-resolve all unresolved conflicts using the given strategy.
   * Returns the number of conflicts resolved.
   */
  async autoResolveConflicts(
    strategy: ConflictResolutionStrategyType = ConflictResolutionStrategy.DENY_WINS,
  ): Promise<{ resolved: number; total: number }> {
    const unresolved = await db.policyConflictRecord.findMany({
      where: { resolved: false },
    });

    if (unresolved.length === 0) {
      return { resolved: 0, total: 0 };
    }

    const resolvedAt = new Date();
    const resolvedBy = "auto-resolver";

    // Batch update all unresolved conflicts
    for (const record of unresolved) {
      // Determine the effective strategy for this conflict
      const effectiveStrategy = this.resolveStrategyForConflict(record, strategy);

      await db.policyConflictRecord.update({
        where: { id: record.id },
        data: {
          resolved: true,
          resolutionStrategy: effectiveStrategy,
          resolvedBy,
          resolutionNote: `Auto-resolved using ${effectiveStrategy} strategy`,
          resolvedAt,
        },
      });
    }

    return { resolved: unresolved.length, total: unresolved.length };
  }

  /**
   * Generate a summary ConflictReport.
   */
  async getConflictReport(): Promise<ConflictReport> {
    const allConflicts = await db.policyConflictRecord.findMany({
      orderBy: { createdAt: "desc" },
    });

    const conflicts = allConflicts.map((r) => this.recordToConflict(r));
    const totalPolicies = await db.declPolicy.count({ where: { isActive: true } });

    const bySeverity = this.emptyBySeverity();
    const byType = this.emptyByType();

    for (const c of conflicts) {
      bySeverity[c.severity] = (bySeverity[c.severity] ?? 0) + 1;
      byType[c.type] = (byType[c.type] ?? 0) + 1;
    }

    const conflictScore = this.computeConflictScore(conflicts);
    const summary = this.formatSummary(conflicts.length, conflictScore, totalPolicies);

    return {
      generatedAt: new Date().toISOString(),
      totalPolicies,
      totalConflicts: conflicts.length,
      bySeverity,
      byType,
      conflicts,
      conflictScore,
      summary,
    };
  }

  /**
   * Query conflicts with filtering options.
   */
  async getConflicts(options?: ConflictDetectionOptions): Promise<PolicyConflict[]> {
    const where: Record<string, unknown> = {};

    if (options?.severity) {
      where.severity = options.severity;
    }
    if (options?.type) {
      where.type = options.type;
    }
    if (options?.resolved !== undefined) {
      where.resolved = options.resolved;
    }
    if (options?.policyId) {
      where.OR = [
        { policyIdA: options.policyId },
        { policyIdB: options.policyId },
      ];
    }

    const records = await db.policyConflictRecord.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: options?.limit ?? 100,
      skip: options?.offset ?? 0,
    });

    return records.map((r) => this.recordToConflict(r));
  }

  // ─── Private: Policy Loading ──────────────────────────────────────

  /**
   * Load policy statements from DB.
   */
  private async loadPolicyStatements(policyIds?: string[]): Promise<LoadedStatement[]> {
    const where: Record<string, unknown> = { isActive: true };
    if (policyIds && policyIds.length > 0) {
      where.policyId = { in: policyIds };
    }

    const policies = await db.declPolicy.findMany({
      where,
      orderBy: { updatedAt: "desc" },
    });

    const statements: LoadedStatement[] = [];

    for (const policy of policies) {
      let parsedStatements: PolicyStatement[];
      try {
        parsedStatements = JSON.parse(policy.statements);
      } catch {
        continue; // Skip policies with invalid JSON
      }

      // Try to resolve namespace from labels
      let namespace: string | undefined;
      try {
        const labels = JSON.parse(policy.labels);
        if (labels && typeof labels === "object") {
          namespace = (labels as Record<string, string>).namespace;
        }
      } catch {
        // No namespace
      }

      for (const stmt of parsedStatements) {
        statements.push({
          policyId: policy.policyId,
          version: policy.version,
          statement: stmt,
          namespace,
        });
      }
    }

    return statements;
  }

  // ─── Private: Statement Pair Analysis ─────────────────────────────

  /**
   * Analyze all statement pairs for conflicts.
   * BUG #7 FIX: Added MAX_STATEMENT_PAIRS limit and early termination
   * to prevent O(N²) explosion on large policy sets.
   * Uses a Visitor-like traversal pattern.
   */
  private analyzeStatementPairs(statements: LoadedStatement[]): PolicyConflict[] {
    const conflicts: PolicyConflict[] = [];
    const seen = new Set<string>();
    const MAX_PAIRS = 50_000; // Safety limit for pair enumeration
    let pairCount = 0;

    for (let i = 0; i < statements.length; i++) {
      for (let j = i + 1; j < statements.length; j++) {
        // BUG #7 FIX: Early termination when pair count exceeds safe limit
        if (++pairCount > MAX_PAIRS) {
          console.warn(
            `[ConflictDetector] Statement pair limit (${MAX_PAIRS}) reached. ` +
            `Analyzed ${i + 1}/${statements.length} statements. ` +
            `Some conflicts may be missed.`
          );
          return conflicts;
        }

        const a = statements[i]!;
        const b = statements[j]!;

        // Skip self-comparison within same statement
        if (a.policyId === b.policyId && a.statement.id === b.statement.id) continue;

        const pairConflicts = this.analyzePair(a, b);
        for (const conflict of pairConflicts) {
          // Deduplicate by generating a unique key
          const key = this.conflictKey(conflict);
          if (!seen.has(key)) {
            seen.add(key);
            conflicts.push(conflict);
          }
        }
      }
    }

    return conflicts;
  }

  /**
   * Analyze a single pair of loaded statements for all possible conflicts.
   */
  private analyzePair(a: LoadedStatement, b: LoadedStatement): PolicyConflict[] {
    const conflicts: PolicyConflict[] = [];
    const stmtA = a.statement;
    const stmtB = b.statement;

    // Check if resource/action patterns overlap
    const patternsOverlap = statementPatternsOverlap(stmtA, stmtB);
    if (!patternsOverlap) return conflicts;

    // Build statement references
    const refA: ConflictStatementRef = {
      policyId: a.policyId,
      version: a.version,
      statementId: stmtA.id,
      effect: stmtA.effect,
      resource: stmtA.resource,
      action: stmtA.action,
    };
    const refB: ConflictStatementRef = {
      policyId: b.policyId,
      version: b.version,
      statementId: stmtB.id,
      effect: stmtB.effect,
      resource: stmtB.resource,
      action: stmtB.action,
    };

