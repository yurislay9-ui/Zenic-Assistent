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

