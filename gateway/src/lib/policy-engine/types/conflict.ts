// ─── 1. Conflict Detection & Resolution ─────────────────────────────────

/** Conflict severity levels */
export const ConflictSeverity = {
  CRITICAL: "critical",  // Direct contradiction: same resource/action, opposite effects
  HIGH: "high",          // Overlapping rules with potential misbehavior
  MEDIUM: "medium",      // Condition overlap that could cause unexpected results
  LOW: "low",            // Redundant rules that don't change outcome
  INFO: "info",          // Informational overlap, no functional impact
} as const;
export type ConflictSeverity = (typeof ConflictSeverity)[keyof typeof ConflictSeverity];

/** Conflict type classification */
export const ConflictType = {
  EFFECT_CONTRADICTION: "effect_contradiction",     // ALLOW vs DENY on same resource/action
  PRIORITY_COLLISION: "priority_collision",          // Same priority, different effects
  CONDITION_OVERLAP: "condition_overlap",            // Overlapping condition scopes
  REDUNDANT_RULE: "redundant_rule",                  // Duplicate or subset rules
  SHADOW_RULE: "shadow_rule",                        // Rule never reached due to higher-priority
  SCOPE_CONFLICT: "scope_conflict",                  // Namespace/policy-set scope overlap
} as const;
export type ConflictType = (typeof ConflictType)[keyof typeof ConflictType];

/** Resolution strategy for conflicts */
export const ConflictResolutionStrategy = {
  DENY_WINS: "deny_wins",             // Deny always takes precedence
  PRIORITY_WINS: "priority_wins",     // Higher priority statement wins
  MERGE_CONDITIONS: "merge_conditions", // Merge conditions (AND logic)
  FIRST_MATCH: "first_match",         // First matching policy wins
  MANUAL: "manual",                   // Requires human resolution
} as const;
export type ConflictResolutionStrategy = (typeof ConflictResolutionStrategy)[keyof typeof ConflictResolutionStrategy];

/** A detected conflict between policy statements */
export interface PolicyConflict {
  /** Unique conflict identifier */
  id: string;
  /** Conflict type */
  type: ConflictType;
  /** Severity level */
  severity: ConflictSeverity;
  /** First conflicting statement */
  statementA: ConflictStatementRef;
  /** Second conflicting statement */
  statementB: ConflictStatementRef;
  /** Human-readable description */
  description: string;
  /** Suggested resolution strategy */
  suggestedResolution: ConflictResolutionStrategy;
  /** Whether this conflict has been resolved */
  resolved: boolean;
  /** Resolution details (if resolved) */
  resolution?: ConflictResolution;
}

/** Reference to a conflicting statement */
export interface ConflictStatementRef {
  /** Policy ID */
  policyId: string;
  /** Policy version */
  version: string;
  /** Statement ID */
  statementId: string;
  /** Statement effect */
  effect: PolicyEffectV2;
  /** Resource pattern */
  resource: string;
  /** Action pattern */
  action: string;
}

/** Resolution applied to a conflict */
export interface ConflictResolution {
  /** Strategy used */
  strategy: ConflictResolutionStrategy;
  /** Who resolved it */
  resolvedBy: string;
  /** When it was resolved */
  resolvedAt: string;
  /** Resolution note */
  note: string;
}

/** Conflict detection report */
export interface ConflictReport {
  /** Report generation timestamp */
  generatedAt: string;
  /** Total policies analyzed */
  totalPolicies: number;
  /** Total conflicts found */
  totalConflicts: number;
  /** Conflicts by severity */
  bySeverity: Record<ConflictSeverity, number>;
  /** Conflicts by type */
  byType: Record<ConflictType, number>;
  /** All detected conflicts */
  conflicts: PolicyConflict[];
  /** Overall conflict score (0-100, lower is better) */
  conflictScore: number;
  /** Summary message */
  summary: string;
}

