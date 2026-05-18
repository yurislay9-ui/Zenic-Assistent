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

