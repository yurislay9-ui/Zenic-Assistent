    (vc) => vc.category === VerdictChangeCategory.NEW_DENY || vc.category === VerdictChangeCategory.CONDITIONAL_TO_DENY,
  ).length;
  const newAllowancesCount = verdictChanges.filter(
    (vc) => vc.category === VerdictChangeCategory.NEW_ALLOW || vc.category === VerdictChangeCategory.CONDITIONAL_TO_ALLOW,
  ).length;

  // Step 9: Build risk factors
  const riskFactors: string[] = [];
  if (newDenialsCount > 0) {
    riskFactors.push(`${newDenialsCount} new denial(s) introduced — may break existing workflows`);
  }
  if (newAllowancesCount > 0) {
    riskFactors.push(`${newAllowancesCount} new allowance(s) — potential security exposure`);
  }
  if (newConflicts.length > 0) {
    const criticalConflicts = newConflicts.filter((c) => c.severity === ConflictSeverity.CRITICAL).length;
    if (criticalConflicts > 0) {
      riskFactors.push(`${criticalConflicts} critical conflict(s) detected in proposed changes`);
    }
  }
  if (complianceImpact.affectedStandards.length > 0) {
    riskFactors.push(`Compliance standards affected: ${complianceImpact.affectedStandards.join(", ")}`);
  }
  if (complianceImpact.scoreChange < 0) {
    riskFactors.push(`Compliance score estimated to decrease by ${Math.abs(complianceImpact.scoreChange)} points`);
  }

  // Step 10: Generate summary
  const summary = generateSummary(
    request.testRequests.length,
    verdictChanges,
    impactScore,
    riskLevel,
    newConflicts,
    resolvedConflicts,
  );

  // Step 11: Build simulation result
  const simulationId = generateSimulationId();
  const simulatedAt = new Date().toISOString();

  const result: SimulationResult = {
    id: simulationId,
    name: request.name,
    totalRequests: request.testRequests.length,
    verdictChanges,
    unchangedCount,
    newConflicts,
    resolvedConflicts,
    impactScore,
    risk: {
      level: riskLevel,
      factors: riskFactors,
      newDenialsCount,
      newAllowancesCount,
      complianceImpact,
    },
    simulatedAt,
    summary,
    trace: request.includeTrace ? traces : undefined,
  };

  // Step 12: Persist to DB
  try {
    await db.policySimulation.create({
      data: {
        simulationId,
        name: request.name,
        description: request.description,
        proposedChanges: JSON.stringify(request.proposedChanges),
        testRequests: JSON.stringify(request.testRequests),
        verdictChanges: JSON.stringify(verdictChanges),
        newConflicts: JSON.stringify(newConflicts),
        resolvedConflicts: JSON.stringify(resolvedConflicts),
        impactScore,
        riskLevel,
        riskFactors: JSON.stringify(riskFactors),
        complianceImpact: JSON.stringify(complianceImpact),
        totalRequests: request.testRequests.length,
        unchangedCount,
        newDenialsCount,
        newAllowancesCount,
        requestedBy: request.requestedBy,
        includeTrace: request.includeTrace,
        trace: JSON.stringify(request.includeTrace ? traces : []),
        summary,
      },
    });
  } catch (error) {
    console.error("[Simulator] Failed to persist simulation result:", error);
    // Still return the result even if DB persistence fails
  }

  return result;
}

/**
 * Find which proposed change caused a verdict difference.
 * Applies changes one at a time and checks when the verdict changes.
 */
function findCausingChange(
  testReq: PolicyEvaluationRequest,
  changes: SimulationChange[],
  evaluator: PolicyEvaluator,
  currentPolicies: PolicyDocument[],
  simulatedPolicies: PolicyDocument[],
): string | undefined {
  const beforeResult = evaluateAgainstPolicySet(evaluator, currentPolicies, testReq);

  // Apply changes incrementally
  let policies = deepClone(currentPolicies);
  for (const change of changes) {
    policies = applySimulationChanges(policies, [change]);
    const intermediateResult = evaluateAgainstPolicySet(evaluator, policies, testReq);
    if (intermediateResult.effect !== beforeResult.effect) {
      return `${change.type}:${change.policyId}`;
    }
  }

  // Fallback: check final simulated result
  const afterResult = evaluateAgainstPolicySet(evaluator, simulatedPolicies, testReq);
  if (afterResult.effect !== beforeResult.effect && changes.length > 0) {
    return `${changes[changes.length - 1]!.type}:${changes[changes.length - 1]!.policyId}`;
  }

  return undefined;
}

/**
 * Load a simulation result from the database.
 *
 * @param simulationId - The unique simulation ID
 * @returns The simulation result, or null if not found
 */
export async function getSimulation(
  simulationId: string,
): Promise<SimulationResult | null> {
  try {
    const record = await db.policySimulation.findUnique({
      where: { simulationId },
    });

    if (!record) return null;

    return mapDbRecordToResult(record);
  } catch (error) {
    console.error("[Simulator] Failed to load simulation:", error);
    return null;
  }
}

/**
 * List simulations with optional filtering and pagination.
 *
 * @param options - Filter and pagination options
 * @returns Array of simulation results
 */
export async function listSimulations(
  options?: ListSimulationsOptions,
): Promise<SimulationResult[]> {
  try {
    const where: Record<string, unknown> = {};

    if (options?.requestedBy) {
      where.requestedBy = options.requestedBy;
    }
    if (options?.riskLevel) {
      where.riskLevel = options.riskLevel;
    }

    const records = await db.policySimulation.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: options?.limit ?? 50,
      skip: options?.offset ?? 0,
    });

    return records.map(mapDbRecordToResult);
  } catch (error) {
    console.error("[Simulator] Failed to list simulations:", error);
    return [];
  }
}

/**
 * Delete a simulation result from the database.
 *
 * @param simulationId - The unique simulation ID to delete
 * @returns True if deleted, false if not found
 */
export async function deleteSimulation(
  simulationId: string,
): Promise<boolean> {
  try {
    const existing = await db.policySimulation.findUnique({
      where: { simulationId },
    });

    if (!existing) return false;

    await db.policySimulation.delete({
      where: { simulationId },
    });

    return true;
  } catch (error) {
    console.error("[Simulator] Failed to delete simulation:", error);
    return false;
  }
}

// ─── DB Record Mapper ────────────────────────────────────────────────

/**
 * Map a Prisma PolicySimulation record to a SimulationResult type.
 */
function mapDbRecordToResult(
  record: {
    simulationId: string;
    name: string;
    totalRequests: number;
    verdictChanges: string;
    unchangedCount: number;
    newConflicts: string;
    resolvedConflicts: string;
    impactScore: number;
    riskLevel: string;
    riskFactors: string;
    complianceImpact: string;
    newDenialsCount: number;
    newAllowancesCount: number;
    trace: string;
    summary: string;
    createdAt: Date;
    includeTrace: boolean;
  },
): SimulationResult {
  const parsedVerdictChanges = JSON.parse(record.verdictChanges) as VerdictChange[];
  const parsedNewConflicts = JSON.parse(record.newConflicts) as PolicyConflict[];
  const parsedResolvedConflicts = JSON.parse(record.resolvedConflicts) as PolicyConflict[];
  const parsedRiskFactors = JSON.parse(record.riskFactors) as string[];
  const parsedComplianceImpact = JSON.parse(record.complianceImpact) as ComplianceImpact;
  const parsedTrace = record.includeTrace
    ? (JSON.parse(record.trace) as SimulationTrace[])
    : undefined;

  return {
    id: record.simulationId,
    name: record.name,
    totalRequests: record.totalRequests,
    verdictChanges: parsedVerdictChanges,
    unchangedCount: record.unchangedCount,
    newConflicts: parsedNewConflicts,
    resolvedConflicts: parsedResolvedConflicts,
    impactScore: record.impactScore,
    risk: {
      level: record.riskLevel as SimulationRiskLevel,
      factors: parsedRiskFactors,
      newDenialsCount: record.newDenialsCount,
      newAllowancesCount: record.newAllowancesCount,
      complianceImpact: parsedComplianceImpact,
    },
    simulatedAt: record.createdAt.toISOString(),
    summary: record.summary,
    trace: parsedTrace,
  };
}
