// ─── Zenic-Agents v3 — Constraint Solver (Internal Types) ──────────
// Internal types used by the constraint solver modules.
// These are NOT the public API types (those live in ../types/constraints.ts).

import type {
  PolicyStatement,
  PolicyCondition,
  PolicyEffectV2,
} from "../types";
import type {
  VerificationStatus,
  SolverType,
  Contradiction,
  ContradictionType,
  UnreachableRule,
  CoverageReport,
  CoverageGap,
  PartialCoverageEntry,
  VerificationResult,
} from "../types/constraints";
import {
  VerificationStatus as VerificationStatusEnum,
  SolverType as SolverTypeEnum,
  ContradictionType as ContradictionTypeEnum,
} from "../types/constraints";
import { PolicyEvaluator } from "../evaluator";

// Re-export public types for convenience
export type {
  VerificationResult,
  VerificationStatus,
  SolverType,
  Contradiction,
  ContradictionType,
  UnreachableRule,
  CoverageReport,
  CoverageGap,
  PartialCoverageEntry,
} from "../types/constraints";

export {
  VerificationStatus as VerificationStatusEnum,
  SolverType as SolverTypeEnum,
  ContradictionType as ContradictionTypeEnum,
} from "../types/constraints";

export type { PolicyDocument, PolicyStatement, PolicyCondition, PolicyEffectV2 } from "../types";

export { PolicyEvaluator } from "../evaluator";

// ─── Solver Configuration ─────────────────────────────────────────────

export const DEFAULT_SOLVER_TIMEOUT_MS = 30_000;
export const BRUTE_FORCE_MAX_POLICIES = 5;
export const MAX_STATEMENT_PAIRS = 50_000; // Safety limit for pair enumeration

// ─── Internal Types ───────────────────────────────────────────────────

/** A condition's value range for constraint analysis */
export interface ConditionRange {
  /** The field being constrained */
  field: string;
  /** Numeric lower bound (if applicable) */
  lowerBound: number | null;
  /** Whether lower bound is inclusive */
  lowerInclusive: boolean;
  /** Numeric upper bound (if applicable) */
  upperBound: number | null;
  /** Whether upper bound is inclusive */
  upperInclusive: boolean;
  /** Discrete allowed values (for eq, in) */
  allowedValues: unknown[] | null;
  /** Discrete disallowed values (for neq, notin) */
  disallowedValues: unknown[] | null;
  /** Whether this is a string-based condition (regex, contains, etc.) */
  isStringBased: boolean;
  /** Whether this is an existence check */
  isExistenceCheck: boolean;
  /** Original conditions contributing to this range */
  originalConditions: PolicyCondition[];
}

/** A statement enriched with constraint analysis data */
export interface AnalyzedStatement {
  /** Source policy ID */
  policyId: string;
  /** Source policy version */
  policyVersion: string;
  /** The original statement */
  statement: PolicyStatement;
  /** Extracted condition ranges per field */
  conditionRanges: Map<string, ConditionRange>;
  /** Whether the statement has no conditions (unconditional) */
  isUnconditional: boolean;
}

/** Arc in the constraint graph */
export interface ConstraintArc {
  /** First statement index */
  i: number;
  /** Second statement index */
  j: number;
}

/** AC-3 domain representation — the set of viable "effects" a statement can produce */
export interface StatementDomain {
  /** Possible effects after constraint propagation */
  possibleEffects: Set<PolicyEffectV2>;
  /** Whether the domain has been reduced */
  reduced: boolean;
}
