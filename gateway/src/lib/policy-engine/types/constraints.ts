// ─── 7. Constraint Solver (Formal Verification) ─────────────────────────

/** Verification result */
export interface VerificationResult {
  /** Whether the policy set is consistent (no contradictions) */
  consistent: boolean;
  /** Whether all possible requests have a matching rule (completeness) */
  complete: boolean;
  /** Whether there are unreachable rules */
  hasUnreachableRules: boolean;
  /** Verification status */
  status: VerificationStatus;
  /** Found contradictions */
  contradictions: Contradiction[];
  /** Unreachable rules */
  unreachableRules: UnreachableRule[];
  /** Coverage report */
  coverage: CoverageReport;
  /** Verification duration in ms */
  duration: number;
  /** Solver type used */
  solverType: SolverType;
  /** Summary */
  summary: string;
}

/** Verification status */
export const VerificationStatus = {
  PASS: "pass",
  FAIL: "fail",
  WARNING: "warning",
  ERROR: "error",
  TIMEOUT: "timeout",
} as const;
export type VerificationStatus = (typeof VerificationStatus)[keyof typeof VerificationStatus];

/** Solver types */
export const SolverType = {
  Z3_SAT: "z3_sat",           // Z3 SAT solver (primary)
  AC3_CSP: "ac3_csp",         // AC-3 constraint propagation (fallback)
  BRUTE_FORCE: "brute_force", // Exhaustive enumeration (small sets)
  HYBRID: "hybrid",           // Combination of approaches
} as const;
export type SolverType = (typeof SolverType)[keyof typeof SolverType];

/** A contradiction found by the solver */
export interface Contradiction {
  /** Contradiction ID */
  id: string;
  /** Type */
  type: ContradictionType;
  /** Conflicting statements */
  statements: Array<{
    policyId: string;
    statementId: string;
    effect: PolicyEffectV2;
  }>;
  /** The condition state that triggers the contradiction */
  triggeringCondition: Record<string, unknown>;
  /** Explanation */
  explanation: string;
  /** Suggested fix */
  suggestedFix: string;
}

/** Contradiction types */
export const ContradictionType = {
  EFFECT_CONFLICT: "effect_conflict",           // Same conditions, opposite effects
  UNSATISFIABLE_CONDITION: "unsatisfiable_condition", // Condition can never be true
  TAUTOLOGY: "tautology",                       // Condition is always true (redundant)
  MUTUAL_EXCLUSION: "mutual_exclusion",         // Rules mutually exclude each other
} as const;
export type ContradictionType = (typeof ContradictionType)[keyof typeof ContradictionType];

/** An unreachable rule */
export interface UnreachableRule {
  /** Policy ID */
  policyId: string;
  /** Statement ID */
  statementId: string;
  /** Reason it's unreachable */
  reason: string;
  /** The statement that shadows it */
  shadowingStatementId?: string;
  /** Shadowing policy ID */
  shadowingPolicyId?: string;
}

/** Coverage report for completeness analysis */
export interface CoverageReport {
  /** Total resource:action space (estimated) */
  totalSpace: number;
  /** Covered space */
  coveredSpace: number;
  /** Coverage percentage (0-100) */
  coveragePct: number;
  /** Uncovered resource:action pairs */
  gaps: CoverageGap[];
  /** Resource patterns with partial coverage */
  partialCoverage: PartialCoverageEntry[];
}

/** A gap in policy coverage */
export interface CoverageGap {
  /** Resource pattern */
  resource: string;
  /** Action pattern */
  action: string;
  /** Why it's uncovered */
  reason: string;
  /** Suggested statement to add */
  suggestedStatement?: Partial<PolicyStatement>;
}

/** Partial coverage entry */
export interface PartialCoverageEntry {
  /** Resource pattern */
  resource: string;
  /** Action pattern */
  action: string;
  /** Covered conditions */
  coveredConditions: string[];
  /** Uncovered conditions */
  uncoveredConditions: string[];
  /** Coverage percentage for this pair */
  coveragePct: number;
}

