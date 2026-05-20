// ─── Pricing Engine Enums ──────────────────────────────────────────────
// Subscription tiers, statuses, payment methods, add-on IDs.
// Extracted from pricing-engine/types.ts for modularity.

// ═══════════════════════════════════════════════════════════════════════════
// Subscription Tier Names: 5 Levels
// ═══════════════════════════════════════════════════════════════════════════

export const SubscriptionTierName = {
  STARTER: "starter",
  BUSINESS: "business",
  ENTERPRISE: "enterprise",
  ON_PREMISE_ENTERPRISE: "on_premise_enterprise",
  TRIAL: "trial",
} as const;
export type SubscriptionTierName = (typeof SubscriptionTierName)[keyof typeof SubscriptionTierName];

// ═══════════════════════════════════════════════════════════════════════════
// Subscription Status
// ═══════════════════════════════════════════════════════════════════════════

export const SubscriptionStatus = {
  TRIAL: "trial",
  ACTIVE: "active",
  PAST_DUE: "past_due",
  CANCELLED: "cancelled",
  EXPIRED: "expired",
  SUSPENDED: "suspended",
  PENDING_PAYMENT: "pending_payment",
} as const;
export type SubscriptionStatus = (typeof SubscriptionStatus)[keyof typeof SubscriptionStatus];

// ═══════════════════════════════════════════════════════════════════════════
// Payment Method — USDT TRC20 ONLY
// ═══════════════════════════════════════════════════════════════════════════

export const PaymentMethod = {
  USDT_TRC20: "usdt_trc20",
} as const;
export type PaymentMethod = (typeof PaymentMethod)[keyof typeof PaymentMethod];

// ═══════════════════════════════════════════════════════════════════════════
// Payment Status
// ═══════════════════════════════════════════════════════════════════════════

export const PaymentStatus = {
  PENDING: "pending",
  CONFIRMING: "confirming",
  CONFIRMED: "confirmed",
  FAILED: "failed",
  EXPIRED: "expired",
  REFUNDED: "refunded",
} as const;
export type PaymentStatus = (typeof PaymentStatus)[keyof typeof PaymentStatus];

// ═══════════════════════════════════════════════════════════════════════════
// Add-on Identifiers
// ═══════════════════════════════════════════════════════════════════════════

export const AddOnId = {
  EXTRA_WORKFLOW_PACK: "ExtraWorkflowPack",
  EXTRA_TEAM_PACK: "ExtraTeamPack",
  COMPLIANCE_PACK: "CompliancePack",
  ADVANCED_ANALYTICS: "AdvancedAnalytics",
  PRIORITY_SUPPORT: "PrioritySupport",
  Z3_SOLVER_ACCESS: "Z3SolverAccess",
  EXTRA_SIMULATIONS_PACK: "ExtraSimulationsPack",
  AUDIT_EXTENDED_RETENTION: "AuditExtendedRetention",
} as const;
export type AddOnId = (typeof AddOnId)[keyof typeof AddOnId];

// ═══════════════════════════════════════════════════════════════════════════
// Payment Verification — Manual/Semi-Manual Only
// ═══════════════════════════════════════════════════════════════════════════

export const PaymentVerificationMethod = {
  MANUAL_ADMIN: "manual_admin",
  SEMI_MANUAL_ONCHAIN: "semi_manual_onchain",
} as const;
export type PaymentVerificationMethod = (typeof PaymentVerificationMethod)[keyof typeof PaymentVerificationMethod];

export const ManualPaymentStatus = {
  AWAITING_PAYMENT: "awaiting_payment",
  AWAITING_TX_HASH: "awaiting_tx_hash",
  AWAITING_CONFIRMATION: "awaiting_confirmation",
  CONFIRMED: "confirmed",
  REJECTED: "rejected",
  EXPIRED: "expired",
} as const;
export type ManualPaymentStatus = (typeof ManualPaymentStatus)[keyof typeof ManualPaymentStatus];
