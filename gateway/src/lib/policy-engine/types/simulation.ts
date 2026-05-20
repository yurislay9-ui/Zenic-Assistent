// ─── 3. Policy Simulation (What-If Analysis) ────────────────────────────

/** A simulation request */
export interface SimulationRequest {
  /** Simulation name */
  name: string;
  /** Description of what's being tested */
  description: string;
  /** Proposed policy changes */
  proposedChanges: SimulationChange[];
  /** Test requests to evaluate */
  testRequests: PolicyEvaluationRequest[];
  /** Whether to include detailed trace */
  includeTrace: boolean;
  /** Requested by */
  requestedBy: string;
}

/** A single proposed change in a simulation */
export interface SimulationChange {
  /** Change type */
  type: SimulationChangeType;
  /** Target policy ID */
  policyId: string;
  /** Target policy version (for modification) */
  version?: string;
  /** The proposed document (for add/modify) */
  document?: PolicyDocument;
  /** Reason for this change */
  reason: string;
}

/** Simulation change types */
export const SimulationChangeType = {
  ADD_POLICY: "add_policy",
  MODIFY_POLICY: "modify_policy",
  REMOVE_POLICY: "remove_policy",
  ADD_STATEMENT: "add_statement",
  MODIFY_STATEMENT: "modify_statement",
  REMOVE_STATEMENT: "remove_statement",
  CHANGE_PRIORITY: "change_priority",
  CHANGE_CONDITION: "change_condition",
} as const;
export type SimulationChangeType = (typeof SimulationChangeType)[keyof typeof SimulationChangeType];

/** Result of a simulation run */
export interface SimulationResult {
  /** Simulation ID */
  id: string;
  /** Simulation name */
  name: string;
  /** Total test requests evaluated */
  totalRequests: number;
  /** Requests whose verdict changed */
  verdictChanges: VerdictChange[];
  /** Requests whose verdict stayed the same */
  unchangedCount: number;
  /** New conflicts introduced by proposed changes */
  newConflicts: PolicyConflict[];
  /** Resolved conflicts (no longer conflicts after changes) */
  resolvedConflicts: PolicyConflict[];
  /** Impact score (0-100, higher = more impact) */
  impactScore: number;
  /** Risk assessment */
  risk: SimulationRisk;
  /** Simulation timestamp */
  simulatedAt: string;
  /** Summary */
  summary: string;
  /** Detailed trace (if requested) */
  trace?: SimulationTrace[];
}

/** A verdict change from simulation */
export interface VerdictChange {
  /** Test request (resource:action) */
  request: string;
  /** Previous effect */
  beforeEffect: PolicyEffectV2;
  /** After proposed changes */
  afterEffect: PolicyEffectV2;
  /** Previous matching statement */
  beforeStatementId?: string;
  /** After matching statement */
  afterStatementId?: string;
  /** Impact category */
  category: VerdictChangeCategory;
  /** Human-readable description */
  description: string;
}

/** Categories of verdict changes */
export const VerdictChangeCategory = {
  NEW_DENY: "new_deny",             // Previously allowed → now denied
  NEW_ALLOW: "new_allow",           // Previously denied → now allowed
  NEW_CONDITIONAL: "new_conditional", // Became conditional
  CONDITIONAL_TO_DENY: "conditional_to_deny",
  CONDITIONAL_TO_ALLOW: "conditional_to_allow",
  EFFECT_UNCHANGED: "effect_unchanged", // Same effect, different reason
} as const;
export type VerdictChangeCategory = (typeof VerdictChangeCategory)[keyof typeof VerdictChangeCategory];

/** Simulation risk assessment */
export interface SimulationRisk {
  /** Risk level */
  level: SimulationRiskLevel;
  /** Risk factors */
  factors: string[];
  /** Number of new denials (most dangerous) */
  newDenialsCount: number;
  /** Number of new allowances */
  newAllowancesCount: number;
  /** Compliance impact */
  complianceImpact: ComplianceImpact;
}

/** Risk levels */
export const SimulationRiskLevel = {
  LOW: "low",
  MEDIUM: "medium",
  HIGH: "high",
  CRITICAL: "critical",
} as const;
export type SimulationRiskLevel = (typeof SimulationRiskLevel)[keyof typeof SimulationRiskLevel];

/** Compliance impact assessment */
export interface ComplianceImpact {
  /** Compliance standards affected */
  affectedStandards: string[];
  /** New compliance gaps introduced */
  newGaps: string[];
  /** Compliance score change */
  scoreChange: number; // negative = worse
}

/** Simulation trace entry */
export interface SimulationTrace {
  /** Request being evaluated */
  request: PolicyEvaluationRequest;
  /** Before evaluation result */
  beforeResult: PolicyEvaluationResult;
  /** After evaluation result */
  afterResult: PolicyEvaluationResult;
  /** Which proposed change caused the difference (if any) */
  causingChange?: string;
}

