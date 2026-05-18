// ─── Main Verification Function ──────────────────────────────────────────
// Orchestrates consistency, completeness, and reachability checks.

import type { PolicyDocument } from "../types";
import type {
  VerificationResult,
  VerificationStatus,
  SolverType,
  Contradiction,
  CoverageReport,
} from "../types/constraints";
import {
  VerificationStatus as VerificationStatusEnum,
  SolverType as SolverTypeEnum,
  ContradictionType as ContradictionTypeEnum,
} from "../types/constraints";
import { PolicyEvaluator } from "../evaluator";
import { loadPolicies, analyzeStatements, runAC3Consistency } from "./consistency";
import { runBruteForceConsistency, runCompletenessCheck } from "./solvers";
import { runReachabilityCheck } from "./_reachability";
import { persistVerification, getVerification, listVerifications } from "./_persistence";
import type { ListVerificationsOptions } from "./_persistence";
import { DEFAULT_SOLVER_TIMEOUT_MS, BRUTE_FORCE_MAX_POLICIES } from "./types";
import { generateContradictionIndex } from "./helpers";

// Re-export sub-module public API for backward compatibility
export { runReachabilityCheck } from "./_reachability";
export { persistVerification, getVerification, listVerifications } from "./_persistence";
export type { ListVerificationsOptions } from "./_persistence";

/**
 * Verify a set of policies for consistency, completeness, and reachability.
 *
 * @param policyIds - Optional array of policy IDs to verify. If not specified, all active policies are verified.
 * @param solverType - The solver algorithm to use. Defaults to AC3_CSP.
 * @returns VerificationResult with contradictions, coverage gaps, and unreachable rules.
 */
export async function verifyPolicies(
  policyIds?: string[],
  solverType?: SolverType,
): Promise<VerificationResult> {
  const startTime = Date.now();
  const effectiveSolverType = solverType ?? SolverTypeEnum.AC3_CSP;
  const timeoutMs = DEFAULT_SOLVER_TIMEOUT_MS;

  try {
    // 1. Load policies from DB
    const policies = await loadPolicies(policyIds);

    if (policies.length === 0) {
      return {
        consistent: true,
        complete: true,
        hasUnreachableRules: false,
        status: VerificationStatusEnum.WARNING,
        contradictions: [],
        unreachableRules: [],
        coverage: { totalSpace: 0, coveredSpace: 0, coveragePct: 100, gaps: [], partialCoverage: [] },
        duration: Date.now() - startTime,
        solverType: effectiveSolverType,
        summary: "No policies found to verify",
      };
    }

    // 2. Analyze statements
    const analyzed = analyzeStatements(policies);

    // 3. Run consistency check based on solver type
    let contradictions: Contradiction[];

    switch (effectiveSolverType) {
      case SolverTypeEnum.BRUTE_FORCE: {
        if (policies.length > BRUTE_FORCE_MAX_POLICIES) {
          contradictions = runAC3Consistency(analyzed, startTime, timeoutMs);
          contradictions.push({
            id: generateContradictionIndex(0, "solver_fallback"),
            type: ContradictionTypeEnum.TAUTOLOGY,
            statements: [],
            triggeringCondition: { note: "Brute-force not applicable, fell back to AC-3" },
            explanation: `Too many policies (${policies.length}) for brute-force solver (max ${BRUTE_FORCE_MAX_POLICIES}), used AC-3 instead`,
            suggestedFix: "Use AC3_CSP or HYBRID solver for larger policy sets",
          });
        } else {
          const evaluator = new PolicyEvaluator();
          contradictions = runBruteForceConsistency(analyzed, evaluator, startTime, timeoutMs);
        }
        break;
      }
      case SolverTypeEnum.HYBRID: {
        // Try AC-3 first
        contradictions = runAC3Consistency(analyzed, startTime, timeoutMs);

        // If no contradictions found with AC-3 and policy count is small, try brute force
        if (contradictions.length === 0 && policies.length <= BRUTE_FORCE_MAX_POLICIES) {
          const remainingTime = timeoutMs - (Date.now() - startTime);
          if (remainingTime > 1000) {
            const evaluator = new PolicyEvaluator();
            const bruteForceResults = runBruteForceConsistency(analyzed, evaluator, startTime, Math.min(remainingTime, timeoutMs));
            contradictions = [...contradictions, ...bruteForceResults];
          }
        }
        break;
      }
      case SolverTypeEnum.Z3_SAT: {
        // Z3 SAT solver is not available — fall back to AC-3
        contradictions = runAC3Consistency(analyzed, startTime, timeoutMs);
        break;
      }
      case SolverTypeEnum.AC3_CSP:
      default: {
        contradictions = runAC3Consistency(analyzed, startTime, timeoutMs);
        break;
      }
    }

    // Check for timeout
    if (Date.now() - startTime > timeoutMs) {
      const result: VerificationResult = {
        consistent: contradictions.length === 0,
        complete: false,
        hasUnreachableRules: false,
        status: VerificationStatusEnum.TIMEOUT,
        contradictions,
        unreachableRules: [],
        coverage: { totalSpace: 0, coveredSpace: 0, coveragePct: 0, gaps: [], partialCoverage: [] },
        duration: Date.now() - startTime,
        solverType: effectiveSolverType,
        summary: `Verification timed out after ${timeoutMs}ms. ${contradictions.length} contradictions found before timeout.`,
      };

      await persistVerification(policyIds ?? [], result);
      return result;
    }

    // 4. Run completeness check
    const coverage = runCompletenessCheck(analyzed, policies);

    // 5. Run reachability check
    const unreachableRules = runReachabilityCheck(analyzed);

    // 6. Determine overall status
    const consistent = contradictions.filter(
      (c) => c.type === ContradictionTypeEnum.EFFECT_CONFLICT || c.type === ContradictionTypeEnum.UNSATISFIABLE_CONDITION,
    ).length === 0;

    const hasUnreachable = unreachableRules.length > 0;

    let status: VerificationStatus;
    if (!consistent) {
      status = VerificationStatusEnum.FAIL;
    } else if (coverage.gaps.length > 0 || hasUnreachable) {
      status = VerificationStatusEnum.WARNING;
    } else {
      status = VerificationStatusEnum.PASS;
    }

    // 7. Build summary
    const parts: string[] = [];
    parts.push(`Verified ${policies.length} policies (${analyzed.length} statements)`);
    if (contradictions.length > 0) {
      const byType = new Map<string, number>();
      for (const c of contradictions) {
        byType.set(c.type, (byType.get(c.type) ?? 0) + 1);
      }
      parts.push(`Found ${contradictions.length} contradictions: ${Array.from(byType.entries()).map(([t, n]) => `${n} ${t}`).join(", ")}`);
    } else {
      parts.push("No contradictions found");
    }
    if (coverage.gaps.length > 0) {
      parts.push(`${coverage.gaps.length} coverage gaps detected (${coverage.coveragePct}% coverage)`);
    }
    if (hasUnreachable) {
      parts.push(`${unreachableRules.length} unreachable rules detected`);
    }

    const result: VerificationResult = {
      consistent,
      complete: coverage.gaps.length === 0,
      hasUnreachableRules: hasUnreachable,
      status,
      contradictions,
      unreachableRules,
      coverage,
      duration: Date.now() - startTime,
      solverType: effectiveSolverType,
      summary: parts.join(". "),
    };

    // 8. Persist results to DB
    await persistVerification(policyIds ?? [], result);

    return result;
  } catch (error) {
    const result: VerificationResult = {
      consistent: false,
      complete: false,
      hasUnreachableRules: false,
      status: VerificationStatusEnum.ERROR,
      contradictions: [],
      unreachableRules: [],
      coverage: { totalSpace: 0, coveredSpace: 0, coveragePct: 0, gaps: [], partialCoverage: [] },
      duration: Date.now() - startTime,
      solverType: effectiveSolverType,
      summary: `Verification error: ${error instanceof Error ? error.message : String(error)}`,
    };

    try {
      await persistVerification(policyIds ?? [], result);
    } catch {
      // Silently fail if we can't persist the error result
    }

    return result;
  }
}
