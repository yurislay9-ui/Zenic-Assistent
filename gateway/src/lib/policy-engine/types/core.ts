// ─── Zenic-Agents v3 — Policy Engine Type System ─────────────────────────
// Phase 3: Declarative Policy Engine with versioning, testing, and compliance
// Phase 4: Advanced Policy Engine — Conflict, Composition, Simulation, Approval,
//          Templates, Impact Analysis, Constraint Solver, Namespaces
//
// Design Patterns:
//   - Value Object: immutable policy documents
//   - Builder: PolicyDocumentBuilder for fluent construction
//   - Strategy: PolicyEvaluator with pluggable condition operators, conflict resolution,
//               merge strategies, template parameter types
//   - Memento: PolicyVersion snapshots for rollback
//   - Visitor: ComplianceMapper traverses policy structure, impact analysis traversal
//   - Composite: PolicySet composes multiple PolicyDocuments
//   - State Machine: Approval workflow lifecycle
//   - Interpreter: Constraint solver expressions
//   - Namespace: Hierarchical scoping with inheritance

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

