// ─── Zenic-Agents v3 — Policy Engine Type System ─────────────────────────
// Phase 3: Declarative Policy Engine with versioning, testing, and compliance
//
// Design Patterns:
//   - Value Object: immutable policy documents
//   - Builder: PolicyDocumentBuilder for fluent construction
//   - Strategy: PolicyEvaluator with pluggable condition operators
//   - Memento: PolicyVersion snapshots for rollback
//   - Visitor: ComplianceMapper traverses policy structure

// ─── Core Enums & Constants ────────────────────────────────────────────

/** Policy API version */
export const POLICY_API_VERSION = "policy.zenic.dev/v1" as const;

/** Policy document kind */
export const POLICY_KIND = "PolicyDocument" as const;

/** Policy statement effects */
export const PolicyEffectV2 = {
  ALLOW: "allow",
  DENY: "deny",
  CONDITIONAL: "conditional",
} as const;
export type PolicyEffectV2 = (typeof PolicyEffectV2)[keyof typeof PolicyEffectV2];

/** Condition operators — extensible strategy pattern */
export const ConditionOperator = {
  EQ: "eq",
  NEQ: "neq",
  IN: "in",
  NOT_IN: "notin",
  GT: "gt",
  LT: "lt",
  GTE: "gte",
  LTE: "lte",
  REGEX: "regex",
  EXISTS: "exists",
  NOT_EXISTS: "not_exists",
  CONTAINS: "contains",
  STARTS_WITH: "starts_with",
  ENDS_WITH: "ends_with",
} as const;
export type ConditionOperator = (typeof ConditionOperator)[keyof typeof ConditionOperator];

/** Policy test expected outcomes */
export const PolicyTestExpectation = {
  ALLOWED: "allowed",
  DENIED: "denied",
  CONDITIONAL: "conditional",
} as const;
export type PolicyTestExpectation = (typeof PolicyTestExpectation)[keyof typeof PolicyTestExpectation];

/** Policy version status */
export const PolicyVersionStatus = {
  DRAFT: "draft",
  ACTIVE: "active",
  SUPERSEDED: "superseded",
  ARCHIVED: "archived",
} as const;
export type PolicyVersionStatus = (typeof PolicyVersionStatus)[keyof typeof PolicyVersionStatus];

/** Diff change types */
export const DiffChangeType = {
  ADDED: "added",
  REMOVED: "removed",
  MODIFIED: "modified",
  UNCHANGED: "unchanged",
} as const;
export type DiffChangeType = (typeof DiffChangeType)[keyof typeof DiffChangeType];

/** Hot-reload event types */
export const HotReloadEventType = {
  POLICY_ADDED: "policy_added",
  POLICY_UPDATED: "policy_updated",
  POLICY_REMOVED: "policy_removed",
  POLICY_RELOADED: "policy_reloaded",
} as const;
export type HotReloadEventType = (typeof HotReloadEventType)[keyof typeof HotReloadEventType];

// ─── Policy Document Structure (YAML-native) ──────────────────────────

/** Policy metadata */
export interface PolicyMetadata {
  /** Unique policy identifier */
  id: string;
  /** Human-readable name */
  name: string;
  /** Semantic version (semver) */
  version: string;
  /** Description of what the policy controls */
  description: string;
  /** Compliance standards this policy maps to */
  compliance?: ComplianceMapping[];
  /** Labels for categorization and filtering */
  labels?: Record<string, string>;
  /** Author of the policy */
  author?: string;
  /** Creation timestamp (ISO 8601) */
  createdAt?: string;
  /** Last update timestamp (ISO 8601) */
  updatedAt?: string;
}

/** Compliance standard mapping */
export interface ComplianceMapping {
  /** Standard name (e.g., "PCI-DSS", "HIPAA", "SOX", "GDPR") */
  standard: string;
  /** Section or control reference (e.g., "1.2.3", "Article 17") */
  sections: string[];
  /** Mapping confidence (0-1) */
  confidence?: number;
}

/** A single policy statement (rule) */
export interface PolicyStatement {
  /** Unique statement identifier within the policy */
  id: string;
  /** Effect when this statement matches */
  effect: PolicyEffectV2;
  /** Resource pattern (e.g., "financial/transfer", "data/*") */
  resource: string;
  /** Action pattern (e.g., "*", "execute", "read") */
  action: string;
  /** Conditions that must ALL be true for this statement to match */
  conditions?: PolicyCondition[];
  /** Priority — higher = evaluated first; deny always wins on tie */
  priority: number;
  /** Human-readable description of the statement */
  description?: string;
  /** Required role for conditional effect */
  requiredRole?: string;
  /** Tags for categorization */
  tags?: string[];
}

/** A single condition in a policy statement */
export interface PolicyCondition {
  /** Field path in the evaluation context (e.g., "amount", "approved", "riskLevel") */
  field: string;
  /** Comparison operator */
  operator: ConditionOperator;
  /** Value to compare against */
  value: unknown;
  /** Human-readable description */
  description?: string;
}

/** A test case for a policy */
export interface PolicyTestCase {
  /** Test name */
  name: string;
  /** Resource to test */
  resource: string;
  /** Action to test */
  action: string;
  /** Context values for evaluation */
  context: Record<string, unknown>;
  /** Expected outcome */
  expected: PolicyTestExpectation;
  /** Expected matching statement ID (optional) */
  expectedStatementId?: string;
  /** Test description */
  description?: string;
}

/** The full declarative policy document */
export interface PolicyDocument {
  /** API version */
  apiVersion: typeof POLICY_API_VERSION;
  /** Document kind */
  kind: typeof POLICY_KIND;
  /** Policy metadata */
  metadata: PolicyMetadata;
  /** Policy statements (rules) */
  statements: PolicyStatement[];
  /** Test cases for this policy */
  tests?: PolicyTestCase[];
}

// ─── Policy Versioning (Git-like) ─────────────────────────────────────

/** A versioned snapshot of a policy */
export interface PolicyVersion {
  /** Version ID (auto-generated) */
  id: string;
  /** Policy ID this version belongs to */
  policyId: string;
  /** Semantic version string */
  version: string;
  /** Content hash (SHA-256 of the canonical JSON) */
  contentHash: string;
  /** The full policy document at this version */
  document: PolicyDocument;
  /** Version status */
  status: PolicyVersionStatus;
  /** Who created this version */
  createdBy: string;
  /** When this version was created */
  createdAt: string;
  /** Change description (commit message) */
  changeDescription: string;
  /** Parent version ID (for history chain) */
  parentVersionId?: string;
}

/** Version creation request */
export interface CreateVersionRequest {
  /** Policy ID */
  policyId: string;
  /** The policy document */
  document: PolicyDocument;
  /** Change description */
  changeDescription: string;
  /** Who is creating this version */
  createdBy: string;
}

// ─── Policy Diff ──────────────────────────────────────────────────────

/** A diff between two policy versions */
export interface PolicyDiff {
  /** Source version */
  fromVersion: string;
  /** Target version */
  toVersion: string;
  /** Metadata changes */
  metadataChanges: DiffEntry[];
  /** Statement changes */
  statementChanges: DiffEntry[];
  /** Test changes */
  testChanges: DiffEntry[];
  /** Summary stats */
  summary: DiffSummary;
}

/** A single diff entry */
export interface DiffEntry {
  /** Change type */
  changeType: DiffChangeType;
  /** Path within the document (e.g., "statements[2].conditions[0]") */
  path: string;
  /** Old value (for modified/removed) */
  oldValue?: unknown;
  /** New value (for modified/added) */
  newValue?: unknown;
  /** Human-readable description */
  description: string;
}

/** Diff summary statistics */
export interface DiffSummary {
  added: number;
  removed: number;
  modified: number;
  unchanged: number;
}

// ─── Policy Test Results ──────────────────────────────────────────────

/** Result of running a single test case */
export interface PolicyTestResult {
  /** Test case name */
  testName: string;
  /** Whether the test passed */
  passed: boolean;
  /** Expected outcome */
  expected: PolicyTestExpectation;
  /** Actual outcome */
  actual: PolicyTestExpectation;
  /** The statement that matched (if any) */
  matchedStatementId?: string;
  /** Error message (if test errored) */
  error?: string;
  /** Evaluation context snapshot */
  evaluationDetails?: PolicyEvaluationResult;
}

/** Result of running all tests for a policy */
export interface PolicyTestSuiteResult {
  /** Policy ID */
  policyId: string;
  /** Policy version tested */
  version: string;
  /** Total tests */
  total: number;
  /** Passed tests */
  passed: number;
  /** Failed tests */
  failed: number;
  /** Errored tests */
  errors: number;
  /** Individual test results */
  results: PolicyTestResult[];
  /** Execution time in ms */
  duration: number;
  /** Whether the suite passed overall */
  suitePassed: boolean;
}

// ─── Policy Evaluation ────────────────────────────────────────────────

/** A request to evaluate against policies */
export interface PolicyEvaluationRequest {
  /** Resource being accessed (e.g., "financial/transfer") */
  resource: string;
  /** Action being performed (e.g., "execute") */
  action: string;
  /** Evaluation context (field values for conditions) */
  context: Record<string, unknown>;
  /** Tenant ID (for multi-tenant) */
  tenantId?: string;
  /** Requesting user ID */
  userId?: string;
  /** Requesting user roles */
  roles?: string[];
}

/** Result of policy evaluation */
export interface PolicyEvaluationResult {
  /** Final effect */
  effect: PolicyEffectV2;
  /** The policy that determined the outcome */
  policyId: string;
  /** The specific statement that matched */
  matchedStatementId?: string;
  /** Human-readable reason */
  reason: string;
  /** All matched statements (for audit) */
  matchedStatements: Array<{
    policyId: string;
    statementId: string;
    effect: PolicyEffectV2;
    priority: number;
  }>;
  /** Evaluation duration in ms */
  duration: number;
  /** Whether this was a deny-by-default */
  denyByDefault: boolean;
  /** Required role (if conditional) */
  requiredRole?: string;
}

// ─── Hot-Reload ───────────────────────────────────────────────────────

/** A hot-reload event */
export interface HotReloadEvent {
  /** Event type */
  type: HotReloadEventType;
  /** Affected policy ID */
  policyId: string;
  /** Policy version affected */
  version?: string;
  /** Timestamp */
  timestamp: string;
  /** Description */
  description: string;
}

/** Hot-reload listener callback */
export type HotReloadListener = (event: HotReloadEvent) => void;

// ─── Compliance Mapping ───────────────────────────────────────────────

/** Compliance report for a policy */
export interface ComplianceReport {
  /** Policy ID */
  policyId: string;
  /** Policy version */
  version: string;
  /** Mapped standards */
  standards: Array<{
    /** Standard name */
    name: string;
    /** Mapped sections */
    sections: Array<{
      /** Section reference */
      ref: string;
      /** Controlling statement IDs */
      statementIds: string[];
      /** Coverage confidence (0-1) */
      confidence: number;
    }>;
    /** Overall coverage for this standard (0-1) */
    coverage: number;
  }>;
  /** Overall compliance score (0-100) */
  overallScore: number;
  /** Uncovered requirements */
  gaps: string[];
}

// ─── Policy Engine Configuration ───────────────────────────────────────

/** Policy engine configuration */
export interface PolicyEngineConfig {
  /** Default effect when no policy matches */
  defaultEffect: PolicyEffectV2;
  /** Whether to deny on evaluation error */
  denyOnError: boolean;
  /** Maximum number of policies to evaluate */
  maxPolicies: number;
  /** Whether to cache evaluation results */
  enableCache: boolean;
  /** Cache TTL in seconds */
  cacheTtlSeconds: number;
  /** Whether hot-reload is enabled */
  enableHotReload: boolean;
  /** Hot-reload check interval in seconds */
  hotReloadIntervalSeconds: number;
  /** Policy file directory (for YAML loading) */
  policyDirectory?: string;
}

/** Default engine configuration */
export const DEFAULT_POLICY_ENGINE_CONFIG: PolicyEngineConfig = {
  defaultEffect: PolicyEffectV2.DENY,
  denyOnError: true,
  maxPolicies: 100,
  enableCache: true,
  cacheTtlSeconds: 300,
  enableHotReload: true,
  hotReloadIntervalSeconds: 30,
};
