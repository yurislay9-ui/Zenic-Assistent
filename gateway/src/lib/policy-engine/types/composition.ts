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

/** PolicySet API version */
export const POLICY_SET_API_VERSION = "policyset.zenic.dev/v1" as const;

/** PolicySet document kind */
export const POLICY_SET_KIND = "PolicySet" as const;

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

