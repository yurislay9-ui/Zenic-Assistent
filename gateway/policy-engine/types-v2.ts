// ─── Zenic-Agents v3 — Advanced Policy Engine Type System ────────────────
// Phase 4: Declarative Versioned Policy Engine — Extended Types
//
// Design Patterns:
//   - Strategy: Conflict resolution, merge strategies, template parameter types
//   - Composite: PolicySet composes multiple PolicyDocuments
//   - State Machine: Approval workflow lifecycle
//   - Builder: Template instantiation with parameter substitution
//   - Visitor: Impact analysis traversal
//   - Interpreter: Constraint solver expressions
//   - Namespace: Hierarchical scoping with inheritance

import type {
  PolicyDocument,
  PolicyStatement,
  PolicyCondition,
  PolicyEffectV2,
  ConditionOperator,
  PolicyEvaluationRequest,
  PolicyEvaluationResult,
  ComplianceMapping,
  PolicyVersion,
} from "./types";

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

// ─── 2. Policy Composition & Merge ──────────────────────────────────────

/** Merge strategy for combining policies */
export const MergeStrategy = {
  UNION: "union",                     // All statements from all policies
  INTERSECTION: "intersection",       // Only statements present in ALL policies
  OVERRIDE: "override",               // Later policies override earlier ones
  EXTEND: "extend",                   // Later policies add to, never remove from
  PRIORITY_MERGE: "priority_merge",   // Merge by statement priority, deny-wins
} as const;
export type MergeStrategy = (typeof MergeStrategy)[keyof typeof MergeStrategy];

/** A policy set (composite of multiple policies) */
export interface PolicySet {
  /** API version */
  apiVersion: typeof POLICY_SET_API_VERSION;
  /** Document kind */
  kind: typeof POLICY_SET_KIND;
  /** Policy set metadata */
  metadata: PolicySetMetadata;
  /** Ordered list of policy references */
  policies: PolicySetEntry[];
  /** Default merge strategy */
  defaultMergeStrategy: MergeStrategy;
  /** Whether to stop evaluation on first DENY */
  denyStopsEvaluation: boolean;
}

export const POLICY_SET_API_VERSION = "policyset.zenic.dev/v1" as const;
export const POLICY_SET_KIND = "PolicySet" as const;

/** Policy set metadata */
export interface PolicySetMetadata {
  /** Unique policy set identifier */
  id: string;
  /** Human-readable name */
  name: string;
  /** Semantic version */
  version: string;
  /** Description */
  description: string;
  /** Namespace this set belongs to */
  namespace?: string;
  /** Labels */
  labels?: Record<string, string>;
  /** Author */
  author?: string;
  /** Creation timestamp */
  createdAt?: string;
  /** Last update timestamp */
  updatedAt?: string;
}

/** An entry in a policy set */
export interface PolicySetEntry {
  /** Policy ID reference */
  policyId: string;
  /** Specific version (optional, defaults to active) */
  version?: string;
  /** Override merge strategy for this entry */
  mergeStrategy?: MergeStrategy;
  /** Priority within the set (higher = evaluated first) */
  priority: number;
  /** Whether this entry is required (set fails if policy not found) */
  required: boolean;
  /** Override statements (applied on top of the policy) */
  overrides?: Partial<PolicyStatement>[];
}

/** Result of composing a policy set */
export interface ComposedPolicyResult {
  /** The composed policy set ID */
  setId: string;
  /** Total policies composed */
  policyCount: number;
  /** Total statements after merge */
  totalStatements: number;
  /** Statements by effect */
  byEffect: Record<PolicyEffectV2, number>;
  /** Conflicts detected during composition */
  conflicts: PolicyConflict[];
  /** The merged document (if requested) */
  mergedDocument?: PolicyDocument;
  /** Merge statistics */
  stats: CompositionStats;
}

/** Composition statistics */
export interface CompositionStats {
  /** Statements from union */
  unionCount: number;
  /** Statements from intersection */
  intersectionCount: number;
  /** Statements overridden */
  overrideCount: number;
  /** Duplicate statements removed */
  duplicatesRemoved: number;
  /** Merge duration in ms */
  mergeDuration: number;
}

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

// ─── 4. Approval Workflow ───────────────────────────────────────────────

/** Approval request status */
export const ApprovalStatus = {
  DRAFT: "draft",
  PENDING_REVIEW: "pending_review",
  APPROVED: "approved",
  REJECTED: "rejected",
  CANCELLED: "cancelled",
  EXPIRED: "expired",
  DEPLOYED: "deployed",
  ROLLED_BACK: "rolled_back",
} as const;
export type ApprovalStatus = (typeof ApprovalStatus)[keyof typeof ApprovalStatus];

/** Approval priority */
export const ApprovalPriority = {
  LOW: "low",
  MEDIUM: "medium",
  HIGH: "high",
  CRITICAL: "critical",
  EMERGENCY: "emergency",
} as const;
export type ApprovalPriority = (typeof ApprovalPriority)[keyof typeof ApprovalPriority];

/** An approval request for a policy change */
export interface PolicyApprovalRequest {
  /** Unique request ID */
  id: string;
  /** Request title */
  title: string;
  /** Description of the proposed change */
  description: string;
  /** Status */
  status: ApprovalStatus;
  /** Priority */
  priority: ApprovalPriority;
  /** The proposed policy document */
  proposedDocument: PolicyDocument;
  /** Target policy ID (for modifications) */
  targetPolicyId?: string;
  /** Previous version (for rollback capability) */
  previousVersion?: string;
  /** Simulation result ID (if what-if was run) */
  simulationId?: string;
  /** Requested by */
  requestedBy: string;
  /** Required approvals count */
  requiredApprovals: number;
  /** Current approvals */
  approvals: ApprovalDecision[];
  /** Required reviewer roles */
  requiredReviewerRoles: string[];
  /** Auto-approve rules (if any match) */
  autoApproveRules: AutoApproveRule[];
  /** Whether auto-approved */
  autoApproved: boolean;
  /** Expiry date */
  expiresAt?: string;
  /** Creation timestamp */
  createdAt: string;
  /** Last update timestamp */
  updatedAt: string;
  /** Deployment timestamp */
  deployedAt?: string;
}

/** An approval decision */
export interface ApprovalDecision {
  /** Reviewer ID */
  reviewerId: string;
  /** Reviewer name */
  reviewerName: string;
  /** Decision */
  decision: "approved" | "rejected";
  /** Reviewer role */
  role: string;
  /** Comment/feedback */
  comment: string;
  /** Decision timestamp */
  decidedAt: string;
}

/** Auto-approve rule */
export interface AutoApproveRule {
  /** Rule name */
  name: string;
  /** Rule description */
  description: string;
  /** Condition to match */
  condition: AutoApproveCondition;
  /** Whether this rule is active */
  enabled: boolean;
  /** Maximum impact score allowed for auto-approve */
  maxImpactScore: number;
}

/** Auto-approve conditions */
export interface AutoApproveCondition {
  /** Policy labels that match */
  labelMatch?: Record<string, string>;
  /** Maximum number of statements changed */
  maxStatementsChanged?: number;
  /** Only allow effect changes in specific direction */
  allowedEffectChanges?: PolicyEffectV2[];
  /** Compliance standards that must NOT be affected */
  excludeComplianceStandards?: string[];
  /** Maximum new denials allowed */
  maxNewDenials?: number;
}

// ─── 5. Policy Template Engine ──────────────────────────────────────────

/** Template API version */
export const TEMPLATE_API_VERSION = "template.zenic.dev/v1" as const;
export const TEMPLATE_KIND = "PolicyTemplate" as const;

/** A policy template with parameterized variables */
export interface PolicyTemplate {
  /** API version */
  apiVersion: typeof TEMPLATE_API_VERSION;
  /** Document kind */
  kind: typeof TEMPLATE_KIND;
  /** Template metadata */
  metadata: TemplateMetadata;
  /** Template parameters */
  parameters: TemplateParameter[];
  /** Policy document template (with variable placeholders) */
  documentTemplate: PolicyDocumentTemplate;
  /** Default values for parameters */
  defaults: Record<string, unknown>;
  /** Constraint rules for parameter values */
  constraints: TemplateConstraint[];
  /** Generated policy count */
  generatedCount: number;
}

/** Template metadata */
export interface TemplateMetadata {
  /** Unique template identifier */
  id: string;
  /** Template name */
  name: string;
  /** Semantic version */
  version: string;
  /** Description */
  description: string;
  /** Category (e.g., "compliance", "security", "industry") */
  category: string;
  /** Industry this template targets */
  industry?: string;
  /** Tags */
  tags?: string[];
  /** Author */
  author?: string;
  /** Creation timestamp */
  createdAt?: string;
  /** Last update timestamp */
  updatedAt?: string;
}

/** A template parameter definition */
export interface TemplateParameter {
  /** Parameter name (used as {{paramName}} in templates) */
  name: string;
  /** Display name */
  displayName: string;
  /** Description */
  description: string;
  /** Parameter type */
  type: TemplateParameterType;
  /** Whether this parameter is required */
  required: boolean;
  /** Default value */
  defaultValue?: unknown;
  /** Allowed values (for enum type) */
  allowedValues?: unknown[];
  /** Validation regex (for string type) */
  validationRegex?: string;
  /** Min value (for number type) */
  minValue?: number;
  /** Max value (for number type) */
  maxValue?: number;
}

/** Template parameter types */
export const TemplateParameterType = {
  STRING: "string",
  NUMBER: "number",
  BOOLEAN: "boolean",
  ENUM: "enum",
  ARRAY: "array",
  OBJECT: "object",
  RESOURCE_PATTERN: "resource_pattern",
  ACTION_PATTERN: "action_pattern",
} as const;
export type TemplateParameterType = (typeof TemplateParameterType)[keyof typeof TemplateParameterType];

/** A policy document template with variable placeholders */
export interface PolicyDocumentTemplate {
  /** Template for metadata.name (supports {{variable}}) */
  name: string;
  /** Template for metadata.description */
  description: string;
  /** Statement templates */
  statements: StatementTemplate[];
  /** Test case templates */
  tests?: TestCaseTemplate[];
  /** Compliance mappings */
  compliance?: ComplianceMapping[];
  /** Labels template */
  labels?: Record<string, string>;
}

/** A statement template with variable placeholders */
export interface StatementTemplate {
  /** Statement ID template */
  id: string;
  /** Effect (can be {{variable}}) */
  effect: string;
  /** Resource pattern template */
  resource: string;
  /** Action pattern template */
  action: string;
  /** Condition templates */
  conditions?: ConditionTemplate[];
  /** Priority (can be {{variable}}) */
  priority: number | string;
  /** Description template */
  description?: string;
  /** Required role template */
  requiredRole?: string;
  /** Tags template */
  tags?: string[];
}

/** A condition template with variable placeholders */
export interface ConditionTemplate {
  /** Field path template */
  field: string;
  /** Operator */
  operator: ConditionOperator;
  /** Value template (can be {{variable}}) */
  value: string;
  /** Description template */
  description?: string;
}

/** A test case template */
export interface TestCaseTemplate {
  /** Test name template */
  name: string;
  /** Resource template */
  resource: string;
  /** Action template */
  action: string;
  /** Context template */
  context: Record<string, string>;
  /** Expected outcome */
  expected: string;
  /** Description template */
  description?: string;
}

/** Template constraint rules */
export interface TemplateConstraint {
  /** Constraint name */
  name: string;
  /** Constraint type */
  type: TemplateConstraintType;
  /** Parameters for the constraint */
  parameters: Record<string, unknown>;
  /** Error message on violation */
  errorMessage: string;
}

/** Template constraint types */
export const TemplateConstraintType = {
  MUTUALLY_EXCLUSIVE: "mutually_exclusive",     // Parameters cannot both be set
  REQUIRES: "requires",                         // One parameter requires another
  RANGE_CONSTRAINT: "range_constraint",         // Numeric range validation
  REGEX_CONSTRAINT: "regex_constraint",         // String pattern validation
  CUSTOM_EXPRESSION: "custom_expression",       // Custom boolean expression
} as const;
export type TemplateConstraintType = (typeof TemplateConstraintType)[keyof typeof TemplateConstraintType];

/** Template instantiation request */
export interface TemplateInstantiationRequest {
  /** Template ID */
  templateId: string;
  /** Parameter values */
  parameters: Record<string, unknown>;
  /** Target policy ID (for the generated policy) */
  targetPolicyId?: string;
  /** Whether to auto-deploy the generated policy */
  autoDeploy: boolean;
  /** Requested by */
  requestedBy: string;
}

/** Template instantiation result */
export interface TemplateInstantiationResult {
  /** Success */
  success: boolean;
  /** Generated policy document */
  document?: PolicyDocument;
  /** Validation errors */
  errors: string[];
  /** Warnings */
  warnings: string[];
  /** Generated policy ID */
  policyId?: string;
  /** Unresolved parameters */
  unresolvedParameters: string[];
}

// ─── 6. Policy Impact Analysis ──────────────────────────────────────────

/** Impact analysis request */
export interface ImpactAnalysisRequest {
  /** Policy ID being changed */
  policyId: string;
  /** Proposed new version */
  proposedVersion?: string;
  /** Proposed new document */
  proposedDocument?: PolicyDocument;
  /** Analysis depth */
  depth: ImpactAnalysisDepth;
  /** Requested by */
  requestedBy: string;
}

/** Analysis depth levels */
export const ImpactAnalysisDepth = {
  QUICK: "quick",           // Direct dependencies only
  STANDARD: "standard",     // Direct + 1 level indirect
  DEEP: "deep",             // Full transitive closure
} as const;
export type ImpactAnalysisDepth = (typeof ImpactAnalysisDepth)[keyof typeof ImpactAnalysisDepth];

/** Impact analysis result */
export interface ImpactAnalysisResult {
  /** Target policy */
  policyId: string;
  /** Analysis timestamp */
  analyzedAt: string;
  /** Direct dependencies (policies that reference this one) */
  directDependencies: DependencyRef[];
  /** Indirect dependencies (transitive) */
  indirectDependencies: DependencyRef[];
  /** Affected policy sets */
  affectedSets: AffectedSetRef[];
  /** Affected playbooks */
  affectedPlaybooks: AffectedPlaybookRef[];
  /** Affected tools */
  affectedTools: AffectedToolRef[];
  /** Blast radius estimation */
  blastRadius: BlastRadius;
  /** Downstream evaluation changes */
  downstreamChanges: DownstreamChange[];
  /** Summary */
  summary: string;
}

/** A dependency reference */
export interface DependencyRef {
  /** Resource ID */
  id: string;
  /** Resource type */
  type: "policy" | "policy_set" | "playbook" | "tool" | "approval";
  /** Resource name */
  name: string;
  /** How it depends on the target */
  dependencyType: DependencyType;
  /** Whether this is a hard dependency (breaks on change) */
  hardDependency: boolean;
}

/** Dependency types */
export const DependencyType = {
  REFERENCES: "references",         // Directly references the policy
  COMPOSED_BY: "composed_by",       // Policy is part of a policy set
  ACTIVATED_BY: "activated_by",     // Playbook activates this policy
  PROTECTED_BY: "protected_by",     // Tool is protected by this policy
  APPROVED_BY: "approved_by",       // Approval references this policy
  INHERITS_FROM: "inherits_from",   // Inherits from this policy
} as const;
export type DependencyType = (typeof DependencyType)[keyof typeof DependencyType];

/** Affected policy set reference */
export interface AffectedSetRef {
  /** Set ID */
  setId: string;
  /** Set name */
  name: string;
  /** Entry priority in the set */
  priority: number;
  /** Whether the set would need re-composition */
  needsRecomposition: boolean;
}

/** Affected playbook reference */
export interface AffectedPlaybookRef {
  /** Playbook ID */
  playbookId: string;
  /** Playbook name */
  name: string;
  /** Industry */
  industry: string;
  /** Policy role in playbook */
  role: string;
  /** Whether playbook compliance score would change */
  complianceScoreChange: number;
}

/** Affected tool reference */
export interface AffectedToolRef {
  /** Tool ID */
  toolId: string;
  /** Tool name */
  name: string;
  /** Risk level */
  riskLevel: string;
  /** Current verdict for this tool */
  currentVerdict: PolicyEffectV2;
  /** Predicted verdict after change */
  predictedVerdict?: PolicyEffectV2;
}

/** Blast radius estimation */
export interface BlastRadius {
  /** Total unique resources affected */
  totalAffectedResources: number;
  /** Total unique users/roles affected */
  totalAffectedUsers: number;
  /** Risk score (0-100) */
  riskScore: number;
  /** Risk level */
  riskLevel: SimulationRiskLevel;
  /** Estimated recovery time (minutes) if rollback needed */
  estimatedRecoveryMinutes: number;
  /** Categories of impact */
  categories: ImpactCategory[];
}

/** Impact category */
export interface ImpactCategory {
  /** Category name */
  name: string;
  /** Number of resources affected */
  affectedCount: number;
  /** Severity */
  severity: ConflictSeverity;
  /** Description */
  description: string;
}

/** A downstream evaluation change */
export interface DownstreamChange {
  /** Request signature (resource:action) */
  request: string;
  /** Current effect */
  currentEffect: PolicyEffectV2;
  /** Predicted effect after change */
  predictedEffect: PolicyEffectV2;
  /** Confidence in prediction (0-1) */
  confidence: number;
  /** Reason for the change */
  reason: string;
}

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

// ─── 8. Policy Namespace & Multi-tenant Scoping ─────────────────────────

/** Namespace API version */
export const NAMESPACE_API_VERSION = "namespace.zenic.dev/v1" as const;
export const NAMESPACE_KIND = "Namespace" as const;

/** A policy namespace for multi-tenant isolation */
export interface PolicyNamespace {
  /** API version */
  apiVersion: typeof NAMESPACE_API_VERSION;
  /** Document kind */
  kind: typeof NAMESPACE_KIND;
  /** Namespace metadata */
  metadata: NamespaceMetadata;
  /** Namespace hierarchy */
  hierarchy: NamespaceHierarchy;
  /** Resolution strategy */
  resolutionStrategy: NamespaceResolutionStrategy;
  /** Isolation level */
  isolationLevel: NamespaceIsolationLevel;
}

/** Namespace metadata */
export interface NamespaceMetadata {
  /** Unique namespace identifier */
  id: string;
  /** Human-readable name */
  name: string;
  /** Description */
  description: string;
  /** Tenant ID this namespace belongs to */
  tenantId: string;
  /** Parent namespace ID (for hierarchy) */
  parentNamespaceId?: string;
  /** Namespace path (e.g., "root/tenant-abc/department-finance") */
  path: string;
  /** Labels */
  labels?: Record<string, string>;
  /** Creation timestamp */
  createdAt?: string;
  /** Last update timestamp */
  updatedAt?: string;
}

/** Namespace hierarchy configuration */
export interface NamespaceHierarchy {
  /** Whether policies inherit from parent namespace */
  inheritFromParent: boolean;
  /** Maximum depth of inheritance */
  maxInheritanceDepth: number;
  /** Conflict resolution between parent and child */
  parentChildResolution: ConflictResolutionStrategy;
  /** Whether child can override parent DENY */
  childCanOverrideParentDeny: boolean;
  /** Whether child can add new ALLOW rules */
  childCanAddAllow: boolean;
}

/** Namespace resolution strategy */
export const NamespaceResolutionStrategy = {
  LOCAL_FIRST: "local_first",         // Check local namespace first, then parent
  PRIORITY_BASED: "priority_based",   // Use statement priority across namespaces
  DENY_WINS: "deny_wins",            // Deny from any namespace wins
  MOST_RESTRICTIVE: "most_restrictive", // Choose the most restrictive verdict
} as const;
export type NamespaceResolutionStrategy = (typeof NamespaceResolutionStrategy)[keyof typeof NamespaceResolutionStrategy];

/** Namespace isolation levels */
export const NamespaceIsolationLevel = {
  STRICT: "strict",           // No cross-namespace visibility
  SELECTIVE: "selective",     // Explicit sharing via policy sets
  INHERITED: "inherited",     // Child inherits parent policies
  SHARED: "shared",           // Full cross-namespace visibility
} as const;
export type NamespaceIsolationLevel = (typeof NamespaceIsolationLevel)[keyof typeof NamespaceIsolationLevel];

/** Namespace resolution result */
export interface NamespaceResolutionResult {
  /** Namespace that resolved the request */
  resolvingNamespace: string;
  /** All namespaces consulted */
  consultedNamespaces: string[];
  /** Inheritance chain used */
  inheritanceChain: string[];
  /** Final evaluation result */
  evaluation: PolicyEvaluationResult;
  /** Whether parent namespace was consulted */
  parentConsulted: boolean;
  /** Whether any inherited rules applied */
  inheritedRulesApplied: boolean;
}

// ─── 9. Advanced Policy Engine Configuration ────────────────────────────

/** Extended engine configuration for Phase 4 */
export interface AdvancedPolicyEngineConfig {
  /** Conflict detection enabled */
  enableConflictDetection: boolean;
  /** Auto-resolve conflicts when detected */
  autoResolveConflicts: boolean;
  /** Default conflict resolution strategy */
  defaultConflictResolution: ConflictResolutionStrategy;
  /** Approval workflow enabled */
  enableApprovalWorkflow: boolean;
  /** Required approvals for policy changes */
  defaultRequiredApprovals: number;
  /** Approval expiry in hours */
  approvalExpiryHours: number;
  /** Simulation enabled */
  enableSimulation: boolean;
  /** Template engine enabled */
  enableTemplates: boolean;
  /** Constraint solver enabled */
  enableConstraintSolver: boolean;
  /** Default solver type */
  defaultSolverType: SolverType;
  /** Solver timeout in ms */
  solverTimeoutMs: number;
  /** Namespace support enabled */
  enableNamespaces: boolean;
  /** Default namespace isolation level */
  defaultIsolationLevel: NamespaceIsolationLevel;
  /** Impact analysis enabled */
  enableImpactAnalysis: boolean;
  /** Default analysis depth */
  defaultAnalysisDepth: ImpactAnalysisDepth;
  /** Maximum simulation requests */
  maxSimulationRequests: number;
}

/** Default advanced configuration */
export const DEFAULT_ADVANCED_CONFIG: AdvancedPolicyEngineConfig = {
  enableConflictDetection: true,
  autoResolveConflicts: false,
  defaultConflictResolution: ConflictResolutionStrategy.DENY_WINS,
  enableApprovalWorkflow: true,
  defaultRequiredApprovals: 1,
  approvalExpiryHours: 72,
  enableSimulation: true,
  enableTemplates: true,
  enableConstraintSolver: true,
  defaultSolverType: SolverType.AC3_CSP,
  solverTimeoutMs: 30000,
  enableNamespaces: true,
  defaultIsolationLevel: NamespaceIsolationLevel.INHERITED,
  enableImpactAnalysis: true,
  defaultAnalysisDepth: ImpactAnalysisDepth.STANDARD,
  maxSimulationRequests: 1000,
};
