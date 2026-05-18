/**
 * Zenic-Agents Subscription Type System: Core
 *
 * Tier names, prices, limits, memory config, and status types.
 * All payments USDT TRC20 only.
 */

// ─── Tier Names ───

export type SubscriptionTierName = 'starter' | 'business' | 'enterprise' | 'on_premise_enterprise';

export const TIER_RANK: Record<SubscriptionTierName, number> = {
  starter: 0,
  business: 1,
  enterprise: 2,
  on_premise_enterprise: 3,
};

export const TIER_PRICES: Record<SubscriptionTierName, { monthly: number; setup: number; annual: number }> = {
  starter: { monthly: 29, setup: 0, annual: 290 },
  business: { monthly: 99, setup: 0, annual: 990 },
  enterprise: { monthly: 299, setup: 0, annual: 2990 },
  on_premise_enterprise: { monthly: 799, setup: 2000, annual: 7990 },
};

export const TIER_DISPLAY_NAMES: Record<SubscriptionTierName, string> = {
  starter: 'Starter',
  business: 'Business',
  enterprise: 'Enterprise',
  on_premise_enterprise: 'On-Premise Enterprise',
};

// ─── Subscription Status ───

export type SubscriptionStatus =
  | 'trial' | 'active' | 'past_due' | 'suspended'
  | 'cancelled' | 'expired' | 'downgraded';

export const ACTIVE_STATUSES: SubscriptionStatus[] = ['trial', 'active'];

// ─── Tier Limits ───

export interface TierLimits {
  maxWorkflows: number;
  maxActionsPerDay: number;
  maxTeamMembers: number;
  maxApiCallsPerMinute: number;
  maxStorageMb: number;
  maxConcurrentSessions: number;
  maxPlaybooks: number;
  maxPolicyRules: number;
  maxApprovalChainDepth: number;
  customPlaybooks: boolean;
  fullObservability: boolean;
  policyEngine: boolean;
  hitlApprovals: boolean;
  merkleAudit: boolean;
  selfHosted: boolean;
}

// Define all tier limits
export const TIER_LIMITS: Record<SubscriptionTierName, TierLimits> = {
  starter: {
    maxWorkflows: 5,
    maxActionsPerDay: 100,
    maxTeamMembers: 3,
    maxApiCallsPerMinute: 30,
    maxStorageMb: 500,
    maxConcurrentSessions: 2,
    maxPlaybooks: 3,
    maxPolicyRules: 10,
    maxApprovalChainDepth: 0,
    customPlaybooks: false,
    fullObservability: false,
    policyEngine: false,
    hitlApprovals: false,
    merkleAudit: false,
    selfHosted: false,
  },
  business: {
    maxWorkflows: 25,
    maxActionsPerDay: 1000,
    maxTeamMembers: 15,
    maxApiCallsPerMinute: 100,
    maxStorageMb: 5000,
    maxConcurrentSessions: 10,
    maxPlaybooks: 25,
    maxPolicyRules: 50,
    maxApprovalChainDepth: 3,
    customPlaybooks: false,
    fullObservability: false,
    policyEngine: true,
    hitlApprovals: false,
    merkleAudit: false,
    selfHosted: false,
  },
  enterprise: {
    maxWorkflows: Infinity,
    maxActionsPerDay: Infinity,
    maxTeamMembers: Infinity,
    maxApiCallsPerMinute: 1000,
    maxStorageMb: Infinity,
    maxConcurrentSessions: Infinity,
    maxPlaybooks: Infinity,
    maxPolicyRules: Infinity,
    maxApprovalChainDepth: 10,
    customPlaybooks: true,
    fullObservability: true,
    policyEngine: true,
    hitlApprovals: true,
    merkleAudit: true,
    selfHosted: false,
  },
  on_premise_enterprise: {
    maxWorkflows: Infinity,
    maxActionsPerDay: Infinity,
    maxTeamMembers: Infinity,
    maxApiCallsPerMinute: Infinity,
    maxStorageMb: Infinity,
    maxConcurrentSessions: Infinity,
    maxPlaybooks: Infinity,
    maxPolicyRules: Infinity,
    maxApprovalChainDepth: Infinity,
    customPlaybooks: true,
    fullObservability: true,
    policyEngine: true,
    hitlApprovals: true,
    merkleAudit: true,
    selfHosted: true,
  },
};

// ─── Memory Chip Feature Gates (per tier) ───

export interface MemoryTierConfig {
  mechanismsAllowed: string[];
  maxMappingsPerMonth: number;
  lruCacheSize: number;
  ontologyAccess: boolean;
  exportImport: boolean;
  customOntology: boolean;
}

export const MEMORY_TIER_CONFIG: Record<SubscriptionTierName, MemoryTierConfig> = {
  starter: {
    mechanismsAllowed: ['schema_drift'],
    maxMappingsPerMonth: 10,
    lruCacheSize: 100,
    ontologyAccess: false,
    exportImport: false,
    customOntology: false,
  },
  business: {
    mechanismsAllowed: ['schema_drift', 'intent_routing'],
    maxMappingsPerMonth: 50,
    lruCacheSize: 500,
    ontologyAccess: false,
    exportImport: false,
    customOntology: false,
  },
  enterprise: {
    mechanismsAllowed: ['schema_drift', 'intent_routing', 'policy_refinement'],
    maxMappingsPerMonth: Infinity,
    lruCacheSize: 2000,
    ontologyAccess: true,
    exportImport: false,
    customOntology: false,
  },
  on_premise_enterprise: {
    mechanismsAllowed: ['schema_drift', 'intent_routing', 'policy_refinement'],
    maxMappingsPerMonth: Infinity,
    lruCacheSize: Infinity,
    ontologyAccess: true,
    exportImport: true,
    customOntology: true,
  },
};

// ─── Subscription Status Transitions ───

/**
 * Legal transitions between subscription statuses.
 * Mirrors the Rust `SubscriptionStatus::can_transition_to` method.
 */
const VALID_TRANSITIONS: Record<SubscriptionStatus, SubscriptionStatus[]> = {
  trial: ['active', 'cancelled', 'expired'],
  active: ['past_due', 'suspended', 'cancelled', 'downgraded'],
  past_due: ['active', 'suspended', 'cancelled'],
  suspended: ['active', 'cancelled'],
  cancelled: [],
  expired: [],
  downgraded: ['active', 'cancelled'],
};

export function canTransitionTo(from: SubscriptionStatus, to: SubscriptionStatus): boolean {
  return VALID_TRANSITIONS[from]?.includes(to) ?? false;
}

// ─── Core Helper Functions ───

export function isSubscriptionActive(status: SubscriptionStatus): boolean {
  return ACTIVE_STATUSES.includes(status);
}

export function getTierLimits(tier: SubscriptionTierName): TierLimits {
  return TIER_LIMITS[tier];
}

export function getMemoryConfig(tier: SubscriptionTierName): MemoryTierConfig {
  return MEMORY_TIER_CONFIG[tier];
}

export function canUpgrade(from: SubscriptionTierName, to: SubscriptionTierName): boolean {
  return TIER_RANK[to] > TIER_RANK[from];
}
