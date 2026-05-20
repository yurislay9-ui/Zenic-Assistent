 * Impact score weights per verdict change category.
 * Configurable to allow different scoring strategies.
 */
const IMPACT_WEIGHTS: Record<VerdictChangeCategory, number> = {
  [VerdictChangeCategory.NEW_DENY]: 15,
  [VerdictChangeCategory.NEW_ALLOW]: 10,
  [VerdictChangeCategory.NEW_CONDITIONAL]: 5,
  [VerdictChangeCategory.CONDITIONAL_TO_DENY]: 10,
  [VerdictChangeCategory.CONDITIONAL_TO_ALLOW]: 5,
  [VerdictChangeCategory.EFFECT_UNCHANGED]: 0,
};

/** Maximum impact score */
const MAX_IMPACT_SCORE = 100;

/**
 * Calculate impact score based on verdict changes.
 * Each category has a configurable weight; total is capped at 100.
 */
function calculateImpactScore(verdictChanges: VerdictChange[]): number {
  let score = 0;
  for (const change of verdictChanges) {
    score += IMPACT_WEIGHTS[change.category] ?? 0;
  }
  return Math.min(score, MAX_IMPACT_SCORE);
}

/**
 * Determine risk level from impact score.
 *   0-20:  LOW
 *  21-50:  MEDIUM
 *  51-80:  HIGH
 *  81-100: CRITICAL
 */
function determineRiskLevel(score: number): SimulationRiskLevel {
  if (score <= 20) return SimulationRiskLevel.LOW;
  if (score <= 50) return SimulationRiskLevel.MEDIUM;
  if (score <= 80) return SimulationRiskLevel.HIGH;
  return SimulationRiskLevel.CRITICAL;
}

// ─── Compliance Impact Assessment ────────────────────────────────────

/**
 * Assess compliance impact of proposed changes.
 * Collects compliance standards from affected policies and estimates
 * score change based on the severity of verdict changes.
 */
function assessComplianceImpact(
  currentPolicies: PolicyDocument[],
  simulatedPolicies: PolicyDocument[],
  changes: SimulationChange[],
  verdictChanges: VerdictChange[],
): ComplianceImpact {
  // Collect affected policy IDs from changes
  const affectedPolicyIds = new Set(changes.map((c) => c.policyId));

  // Also include policies referenced in verdict changes
  for (const vc of verdictChanges) {
    // Parse the request string (format: "resource:action")
    // Not directly useful for policy ID, but verdict changes indicate affected areas
    void vc; // acknowledge
  }

  // Collect compliance standards from affected policies
  const affectedStandards: string[] = [];
  const standardSections = new Map<string, Set<string>>();

  for (const policy of currentPolicies) {
    if (!affectedPolicyIds.has(policy.metadata.id)) continue;
    const compliance = policy.metadata.compliance ?? [];
    for (const mapping of compliance) {
      if (!affectedStandards.includes(mapping.standard)) {
        affectedStandards.push(mapping.standard);
      }
      const existing = standardSections.get(mapping.standard) ?? new Set<string>();
      for (const section of mapping.sections) {
        existing.add(section);
      }
      standardSections.set(mapping.standard, existing);
    }
  }

  // Also check simulated policies for new compliance mappings
  for (const policy of simulatedPolicies) {
    if (!affectedPolicyIds.has(policy.metadata.id)) continue;
    const compliance = policy.metadata.compliance ?? [];
    for (const mapping of compliance) {
      if (!affectedStandards.includes(mapping.standard)) {
        affectedStandards.push(mapping.standard);
      }
    }
  }

  // Identify new compliance gaps introduced by verdict changes
  const newGaps: string[] = [];
  const newDenials = verdictChanges.filter(
    (vc) => vc.category === VerdictChangeCategory.NEW_DENY,
  );
  const newAllowances = verdictChanges.filter(
    (vc) => vc.category === VerdictChangeCategory.NEW_ALLOW,
  );

  // New denials may create operational gaps
  for (const denial of newDenials) {
    newGaps.push(`Potential operational gap: ${denial.request} now denied`);
  }

  // New allowances may create compliance gaps
  for (const allowance of newAllowances) {
    for (const standard of affectedStandards) {
      newGaps.push(`Compliance risk: ${allowance.request} now allowed — may violate ${standard}`);
    }
  }

  // Estimate compliance score change
  // Negative means worse compliance posture
  let scoreChange = 0;
  for (const vc of verdictChanges) {
    switch (vc.category) {
      case VerdictChangeCategory.NEW_DENY:
        scoreChange -= 2; // New denials may break operations
        break;
      case VerdictChangeCategory.NEW_ALLOW:
        scoreChange -= 5; // New allowances may violate compliance
        break;
      case VerdictChangeCategory.CONDITIONAL_TO_DENY:
        scoreChange -= 1;
        break;
      case VerdictChangeCategory.CONDITIONAL_TO_ALLOW:
        scoreChange -= 3;
        break;
      case VerdictChangeCategory.NEW_CONDITIONAL:
        scoreChange -= 1;
        break;
      case VerdictChangeCategory.EFFECT_UNCHANGED:
        scoreChange += 0;
        break;
    }
  }

  return {
    affectedStandards,
    newGaps,
    scoreChange,
  };
}

// ─── Summary Generation ──────────────────────────────────────────────

/**
 * Generate a human-readable summary for a simulation result.
 */
function generateSummary(
  totalRequests: number,
  verdictChanges: VerdictChange[],
  impactScore: number,
  riskLevel: SimulationRiskLevel,
  newConflicts: PolicyConflict[],
  resolvedConflicts: PolicyConflict[],
): string {
  const lines: string[] = [];

  lines.push(`Simulation analyzed ${totalRequests} test request(s).`);

  if (verdictChanges.length === 0) {
    lines.push("No verdict changes detected — proposed changes have no impact on current evaluations.");
  } else {
    const byCategory = new Map<VerdictChangeCategory, number>();
    for (const vc of verdictChanges) {
      byCategory.set(vc.category, (byCategory.get(vc.category) ?? 0) + 1);
    }

    lines.push(`${verdictChanges.length} verdict change(s) detected:`);
    for (const [category, count] of byCategory) {
      lines.push(`  - ${category}: ${count}`);
    }
  }

  lines.push(`Impact score: ${impactScore}/100 (${riskLevel} risk).`);

  if (newConflicts.length > 0) {
    lines.push(`${newConflicts.length} new conflict(s) introduced.`);
  }
  if (resolvedConflicts.length > 0) {
    lines.push(`${resolvedConflicts.length} conflict(s) resolved.`);
  }

  return lines.join(" ");
}

// ─── Public API ──────────────────────────────────────────────────────

/**
 * Run a what-if simulation.
 *
 * Loads current active policies, applies proposed changes to create
 * a simulated set, evaluates each test request against both sets,
 * detects conflicts, calculates impact, and persists the result.
 *
 * @param request - Simulation request with proposed changes and test requests
 * @returns Simulation result with verdict changes, impact score, and risk assessment
 */
export async function runSimulation(
  request: SimulationRequest,
): Promise<SimulationResult> {
  const evaluator = getPolicyEvaluator();

  // Step 1: Load current active policies
  const currentPolicies = await loadActivePoliciesFromDb();

  // Step 2: Apply proposed changes to create simulated set
  const simulatedPolicies = applySimulationChanges(currentPolicies, request.proposedChanges);

  // Step 3: Evaluate each test request against both sets
  const verdictChanges: VerdictChange[] = [];
  const traces: SimulationTrace[] = [];
  let unchangedCount = 0;

  for (const testReq of request.testRequests) {
    // Evaluate against current policies
    const beforeResult = evaluateAgainstPolicySet(evaluator, currentPolicies, testReq);

    // Evaluate against simulated policies
    const afterResult = evaluateAgainstPolicySet(evaluator, simulatedPolicies, testReq);

    // Record trace if requested
    if (request.includeTrace) {
      traces.push({
        request: testReq,
        beforeResult,
        afterResult,
        causingChange: beforeResult.effect !== afterResult.effect
          ? findCausingChange(testReq, request.proposedChanges, evaluator, currentPolicies, simulatedPolicies)
          : undefined,
      });
    }

    // Compare results
    const requestSignature = `${testReq.resource}:${testReq.action}`;

    if (beforeResult.effect !== afterResult.effect) {
      // Verdict changed
      const category = classifyVerdictChange(beforeResult.effect, afterResult.effect);
      verdictChanges.push({
        request: requestSignature,
        beforeEffect: beforeResult.effect,
        afterEffect: afterResult.effect,
        beforeStatementId: beforeResult.matchedStatementId,
        afterStatementId: afterResult.matchedStatementId,
        category,
        description: describeVerdictChange(
          requestSignature,
          beforeResult.effect,
          afterResult.effect,
          category,
        ),
      });
    } else if (beforeResult.matchedStatementId !== afterResult.matchedStatementId) {
      // Same effect but different matched statement
      verdictChanges.push({
        request: requestSignature,
        beforeEffect: beforeResult.effect,
        afterEffect: afterResult.effect,
        beforeStatementId: beforeResult.matchedStatementId,
        afterStatementId: afterResult.matchedStatementId,
        category: VerdictChangeCategory.EFFECT_UNCHANGED,
        description: describeVerdictChange(
          requestSignature,
          beforeResult.effect,
          afterResult.effect,
          VerdictChangeCategory.EFFECT_UNCHANGED,
        ),
      });
    } else {
      unchangedCount++;
    }
  }

  // Step 4: Run conflict detection on both sets
  const currentConflicts = detectPolicyConflicts(currentPolicies);
  const simulatedConflicts = detectPolicyConflicts(simulatedPolicies);
  const { newConflicts, resolvedConflicts } = diffConflicts(currentConflicts, simulatedConflicts);

  // Step 5: Calculate impact score
  const impactScore = calculateImpactScore(verdictChanges);

  // Step 6: Determine risk level
  const riskLevel = determineRiskLevel(impactScore);

  // Step 7: Assess compliance impact
  const complianceImpact = assessComplianceImpact(
    currentPolicies,
    simulatedPolicies,
    request.proposedChanges,
    verdictChanges,
  );

  // Step 8: Count denials and allowances
  const newDenialsCount = verdictChanges.filter(
