// ─── 8. Policy Namespace & Multi-tenant Scoping ─────────────────────────

/** Namespace API version */
export const NAMESPACE_API_VERSION = "namespace.zenic.dev/v1" as const;

/** Namespace document kind */
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
