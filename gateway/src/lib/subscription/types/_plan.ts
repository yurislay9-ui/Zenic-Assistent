/**
 * Zenic-Agents Subscription Type System: Plans & Features
 *
 * Feature gates, add-ons, payment types, subscription, usage, and helpers.
 * All payments USDT TRC20 only.
 */

import type { SubscriptionTierName, SubscriptionStatus } from "./_core";
import {
  TIER_RANK,
  TIER_PRICES,
  ACTIVE_STATUSES,
} from "./_core";

// Re-export core types for convenience
export type { SubscriptionTierName, SubscriptionStatus } from "./_core";

// ─── Feature Gates (ALL features mapped to tiers) ───

export interface FeatureGateDefinition {
  feature: string;
  description: string;
  minimumTier: SubscriptionTierName;
  availableAsAddon: boolean;
  addonId?: string;
}

/**
 * Comprehensive feature gate mapping for ALL Zenic-Agents features.
 * Maps 70+ features across all modules to subscription tiers.
 */
export const FEATURE_GATES: FeatureGateDefinition[] = [
  // === Core Pipeline (9 deterministic tasks) ===
  { feature: 'basic_pipeline', description: 'Basic IA pipeline (memory_lookup → classify_intent → extract_entities)', minimumTier: 'starter', availableAsAddon: false },
  { feature: 'full_pipeline', description: 'Full 9-step deterministic pipeline', minimumTier: 'business', availableAsAddon: false },
  { feature: 'chat_completions', description: 'Chat completion API', minimumTier: 'starter', availableAsAddon: false },
  { feature: 'app_generation', description: 'Application generation', minimumTier: 'business', availableAsAddon: false },
  { feature: 'automation_generation', description: 'Automation generation', minimumTier: 'business', availableAsAddon: false },
  { feature: 'schema_design', description: 'Schema design tools', minimumTier: 'business', availableAsAddon: false },
  { feature: 'thinking_engine', description: 'Thinking engine (advanced reasoning)', minimumTier: 'business', availableAsAddon: false },
  { feature: 'reasoning_engine', description: 'Reasoning engine (deep analysis)', minimumTier: 'business', availableAsAddon: false },
  { feature: 'logic_chains', description: 'Logic chain builder', minimumTier: 'business', availableAsAddon: false },

  // === 9 Deterministic Pipeline Tasks ===
  { feature: 'task_memory_lookup', description: 'Step 1: Memory lookup (Chip de Memoria)', minimumTier: 'starter', availableAsAddon: false },
  { feature: 'task_classify_intent', description: 'Step 2: Classify intent', minimumTier: 'starter', availableAsAddon: false },
  { feature: 'task_extract_entities', description: 'Step 3: Extract entities', minimumTier: 'starter', availableAsAddon: false },
  { feature: 'task_validate_schema', description: 'Step 4: Validate schema', minimumTier: 'starter', availableAsAddon: false },
  { feature: 'task_dag_node_adapt', description: 'Step 5: DAG node adaptation (Chip → DAG)', minimumTier: 'business', availableAsAddon: false },
  { feature: 'task_check_rbac', description: 'Step 6: Check RBAC policies', minimumTier: 'business', availableAsAddon: false },
  { feature: 'task_gather_context', description: 'Step 7: Gather context', minimumTier: 'business', availableAsAddon: false },
  { feature: 'task_route_mcp', description: 'Step 8: Route to MCP tool', minimumTier: 'business', availableAsAddon: false },
  { feature: 'task_simulate_dry_run', description: 'Step 9: Simulate dry run', minimumTier: 'enterprise', availableAsAddon: false },

  // === MCP Gateway (Phase 1) ===
  { feature: 'mcp_gateway', description: 'MCP Protocol Gateway', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'mcp_tools_register', description: 'Register custom MCP tools', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'mcp_rate_limit_custom', description: 'Custom rate limit algorithms', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'mcp_audit_full', description: 'Full MCP audit trail', minimumTier: 'enterprise', availableAsAddon: false },

  // === RBAC ===
  { feature: 'rbac_basic', description: 'Basic RBAC (3 roles: viewer, operator, admin)', minimumTier: 'business', availableAsAddon: false },
  { feature: 'rbac_full', description: 'Full RBAC (18 permissions, custom roles)', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'rbac_dangerous_actions', description: 'Dangerous action approval flow', minimumTier: 'enterprise', availableAsAddon: false },

  // === Observability (Phase 2) ===
  { feature: 'observability_basic', description: 'Basic observability (traces, metrics)', minimumTier: 'business', availableAsAddon: true, addonId: 'advanced_analytics' },
  { feature: 'observability_full', description: 'Full observability (export, custom dashboards)', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'observability_export', description: 'Export traces/metrics to external systems', minimumTier: 'enterprise', availableAsAddon: false },

  // === Playbooks (Phase 3) ===
  { feature: 'playbook_library', description: 'Access to playbook library', minimumTier: 'business', availableAsAddon: false },
  { feature: 'playbook_custom', description: 'Create custom playbooks', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'playbook_roi', description: 'ROI calculation and tracking', minimumTier: 'business', availableAsAddon: false },

  // === Policy Engine (Phase 4) ===
  { feature: 'policy_engine_basic', description: 'Basic policy engine (10 rules)', minimumTier: 'business', availableAsAddon: true, addonId: 'policy_engine' },
  { feature: 'policy_engine_full', description: 'Full policy engine (unlimited rules, Z3 solver)', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'policy_compliance_mapping', description: 'Compliance mapping (30+ standards)', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'policy_conflict_detection', description: 'Conflict detection (Z3+AC-3 solver)', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'policy_versioning', description: 'Policy versioning and rollback', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'policy_simulation', description: 'Policy simulation and impact analysis', minimumTier: 'enterprise', availableAsAddon: false },

  // === HITL (Phase 5) ===
  { feature: 'hitl_approvals', description: 'Human-in-the-loop approval chains', minimumTier: 'business', availableAsAddon: true, addonId: 'hitl_approvals' },
  { feature: 'hitl_reversible_actions', description: 'Reversible actions (Memento pattern)', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'hitl_delegation', description: 'Approval delegation', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'hitl_escalation', description: 'Escalation workflows', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'hitl_evidence', description: 'Evidence collection for approvals', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'hitl_sla_tracking', description: 'SLA tracking for approval chains', minimumTier: 'enterprise', availableAsAddon: false },

  // === Chip de Memoria Adaptativa Binaria (Memory) ===
  { feature: 'memory_schema_drift', description: 'Schema Drift detection', minimumTier: 'starter', availableAsAddon: false },
  { feature: 'memory_intent_routing', description: 'Intent Routing', minimumTier: 'business', availableAsAddon: false },
  { feature: 'memory_policy_refinement', description: 'Policy Refinement', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'memory_ontology_access', description: 'Shared Ontology Base access', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'memory_export_import', description: 'Memory export/import', minimumTier: 'on_premise_enterprise', availableAsAddon: false },
  { feature: 'memory_custom_ontology', description: 'Custom ontology definitions', minimumTier: 'on_premise_enterprise', availableAsAddon: false },

  // === 19 Action Executors ===
  { feature: 'executor_basic', description: 'Basic executors (file, shell, http)', minimumTier: 'starter', availableAsAddon: false },
  { feature: 'executor_database', description: 'Database executor (SQLite, journal rollback)', minimumTier: 'business', availableAsAddon: false },
  { feature: 'executor_transform', description: 'Transform executor (mapping, filtering, aggregation)', minimumTier: 'business', availableAsAddon: false },
  { feature: 'executor_email', description: 'Email executor (SMTP + Graph API)', minimumTier: 'business', availableAsAddon: false },
  { feature: 'executor_jira', description: 'Jira executor (10 operations)', minimumTier: 'business', availableAsAddon: false },
  { feature: 'executor_servicenow', description: 'ServiceNow executor (7 operations)', minimumTier: 'business', availableAsAddon: false },
  { feature: 'executor_schedule', description: 'Schedule executor (APScheduler)', minimumTier: 'business', availableAsAddon: false },
  { feature: 'executor_safety_gate', description: 'Safety Gate executor', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'executor_policy_engine', description: 'Policy Engine executor', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'executor_audit_logger', description: 'Merkle Audit Logger executor', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'executor_impact_preview', description: 'Impact Preview executor', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'executor_dry_run', description: 'Dry Run executor', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'executor_simulation', description: 'Simulation executor', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'executor_diff_preview', description: 'Diff Preview executor', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'executor_coordinated_rollback', description: 'Coordinated Rollback executor', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'executor_blueprint_schema', description: 'Blueprint Schema executor', minimumTier: 'business', availableAsAddon: false },
  { feature: 'executor_action_dispatcher', description: 'Action Dispatcher executor', minimumTier: 'business', availableAsAddon: false },
  { feature: 'executor_db_transaction_journal', description: 'DB Transaction Journal executor', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'executor_all', description: 'All 19 executors unlocked', minimumTier: 'enterprise', availableAsAddon: false },

  // === Merkle Audit ===
  { feature: 'merkle_audit', description: 'Merkle tree audit logging', minimumTier: 'enterprise', availableAsAddon: false },

  // === Verdict Engine (4-Layer) ===
  { feature: 'verdict_deterministic', description: 'Layer 1: Deterministic pipeline verdicts', minimumTier: 'starter', availableAsAddon: false },
  { feature: 'verdict_evidence', description: 'Layer 2: Evidence collector', minimumTier: 'business', availableAsAddon: false },
  { feature: 'verdict_consensus', description: 'Layer 3: Consensus resolver', minimumTier: 'business', availableAsAddon: false },
  { feature: 'verdict_full', description: 'Full 4-layer verdict architecture (IA binary on tie)', minimumTier: 'enterprise', availableAsAddon: false },

  // === DAG Adapter ===
  { feature: 'dag_basic', description: 'Basic DAG execution', minimumTier: 'starter', availableAsAddon: false },
  { feature: 'dag_adapt_middleware', description: 'DAG Adapter middleware (Chip → DAG parameter injection)', minimumTier: 'business', availableAsAddon: false },
  { feature: 'dag_batch_adapt', description: 'Batch DAG adaptation', minimumTier: 'enterprise', availableAsAddon: false },

  // === Self-Hosted / On-Premise ===
  { feature: 'self_hosted', description: 'Self-hosted deployment', minimumTier: 'on_premise_enterprise', availableAsAddon: false },
  { feature: 'white_label', description: 'White-label branding', minimumTier: 'on_premise_enterprise', availableAsAddon: false },
  { feature: 'source_code_access', description: 'Source code access', minimumTier: 'on_premise_enterprise', availableAsAddon: false },
  { feature: 'custom_integrations', description: 'Custom integration development', minimumTier: 'on_premise_enterprise', availableAsAddon: false },
  { feature: 'air_gap', description: 'Air-gap capable deployment', minimumTier: 'on_premise_enterprise', availableAsAddon: false },
  { feature: 'military_encryption', description: 'Military-grade encryption', minimumTier: 'on_premise_enterprise', availableAsAddon: false },

  // === API Rate Limits ===
  { feature: 'api_rate_30', description: '30 API calls/minute', minimumTier: 'starter', availableAsAddon: false },
  { feature: 'api_rate_100', description: '100 API calls/minute', minimumTier: 'business', availableAsAddon: false },
  { feature: 'api_rate_1000', description: '1000 API calls/minute', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'api_rate_unlimited', description: 'Unlimited API calls', minimumTier: 'on_premise_enterprise', availableAsAddon: false },

  // === Support ===
  { feature: 'community_support', description: 'Community support', minimumTier: 'starter', availableAsAddon: false },
  { feature: 'priority_support', description: 'Priority support', minimumTier: 'business', availableAsAddon: false },
  { feature: 'dedicated_support', description: 'Dedicated support engineer', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'dedicated_engineer', description: 'Dedicated on-site engineer', minimumTier: 'on_premise_enterprise', availableAsAddon: false },

  // === SLA ===
  { feature: 'sla_standard', description: 'Standard SLA (99.5%)', minimumTier: 'starter', availableAsAddon: false },
  { feature: 'sla_high', description: 'High availability SLA (99.9%)', minimumTier: 'enterprise', availableAsAddon: false },
  { feature: 'sla_custom', description: 'Custom SLA', minimumTier: 'on_premise_enterprise', availableAsAddon: false },
];

// ─── Add-Ons ───

export interface AddOnDefinition {
  id: string;
  name: string;
  monthlyPriceUsdt: number;
  description: string;
  compatibleTiers: SubscriptionTierName[];
}

export const ADD_ONS: AddOnDefinition[] = [
  { id: 'extra_workflows_10', name: 'Extra Workflows (+10)', monthlyPriceUsdt: 10, description: 'Add 10 additional workflow slots', compatibleTiers: ['starter', 'business'] },
  { id: 'extra_team_members_5', name: 'Extra Team Members (+5)', monthlyPriceUsdt: 15, description: 'Add 5 additional team member seats', compatibleTiers: ['starter', 'business'] },
  { id: 'advanced_analytics', name: 'Advanced Analytics', monthlyPriceUsdt: 25, description: 'Full observability dashboard and analytics', compatibleTiers: ['starter', 'business'] },
  { id: 'policy_engine', name: 'Policy Engine', monthlyPriceUsdt: 30, description: 'Compliance mapping and policy enforcement', compatibleTiers: ['business'] },
  { id: 'hitl_approvals', name: 'HITL Approvals', monthlyPriceUsdt: 35, description: 'Human-in-the-loop approval chains', compatibleTiers: ['business'] },
];

// ─── Payment ───

export type PaymentMethod = 'manual' | 'semi_manual';

export type PaymentStatus = 'pending' | 'tx_submitted' | 'verifying' | 'confirmed' | 'expired' | 'failed';

export interface UsdtPayment {
  id: string;
  subscriptionId: string;
  tenantId: string;
  amountUsdt: number;
  method: PaymentMethod;
  companyWallet: string;
  sourceWallet?: string;
  txHash?: string;
  blockNumber?: number;
  status: PaymentStatus;
  includesSetupFee: boolean;
  setupFeeAmountUsdt: number;
  verificationAttempts: number;
  maxVerificationAttempts: number;
  expiresAt: string;
  confirmedAt?: string;
  confirmedBy?: string;
  notes?: string;
  createdAt: string;
}

// ─── Trial ───

export interface Trial {
  id: string;
  tenantId: string;
  tier: SubscriptionTierName;
  startedAt: string;
  expiresAt: string;
  status: 'active' | 'converted' | 'expired' | 'cancelled';
  convertedAt?: string;
}

// ─── Subscription ───

export interface Subscription {
  id: string;
  tenantId: string;
  tier: SubscriptionTierName;
  status: SubscriptionStatus;
  trialId?: string;
  addOns: string[];
  createdAt: string;
  currentPeriodStart: string;
  currentPeriodEnd: string;
  cancelledAt?: string;
  paymentWalletAddress?: string;
  setupFeePaid: boolean;
}

// ─── Usage Record ───

export type UsageType =
  | 'workflows' | 'actions_daily' | 'team_members'
  | 'api_calls_per_minute' | 'storage_mb' | 'concurrent_sessions'
  | 'playbooks' | 'policy_rules' | 'approval_chain_depth';

export interface UsageRecord {
  tenantId: string;
  usageType: UsageType;
  currentValue: number;
  limitValue: number;
  updatedAt: string;
}

// ─── Helper Functions ───

export function isFeatureAvailable(
  feature: string,
  tier: SubscriptionTierName,
  activeAddons: string[] = []
): boolean {
  const gate = FEATURE_GATES.find(g => g.feature === feature);
  if (!gate) return false; // Unknown features blocked by default

  if (TIER_RANK[tier] >= TIER_RANK[gate.minimumTier]) return true;

  if (gate.availableAsAddon && gate.addonId) {
    return activeAddons.includes(gate.addonId);
  }

  return false;
}

export function calculateFirstPayment(tier: SubscriptionTierName, addOnIds: string[] = []): number {
  const setup = TIER_PRICES[tier].setup;
  const monthly = TIER_PRICES[tier].monthly;
  const addonCost = ADD_ONS.filter(a => addOnIds.includes(a.id)).reduce((sum, a) => sum + a.monthlyPriceUsdt, 0);
  return setup + monthly + addonCost;
}

export function calculateUpgradeProration(
  fromTier: SubscriptionTierName,
  toTier: SubscriptionTierName,
  daysRemaining: number
): number {
  if (!TIER_RANK[toTier] || !TIER_RANK[fromTier]) return 0;
  if (TIER_RANK[toTier] <= TIER_RANK[fromTier]) return 0;
  const fromDaily = TIER_PRICES[fromTier].monthly / 30;
  const toDaily = TIER_PRICES[toTier].monthly / 30;
  return Math.ceil((toDaily - fromDaily) * daysRemaining);
}

export function getFeaturesForTier(tier: SubscriptionTierName): FeatureGateDefinition[] {
  return FEATURE_GATES.filter(g => TIER_RANK[tier] >= TIER_RANK[g.minimumTier]);
}

export function getUnavailableFeaturesForTier(tier: SubscriptionTierName): FeatureGateDefinition[] {
  return FEATURE_GATES.filter(g => TIER_RANK[tier] < TIER_RANK[g.minimumTier]);
}

/**
 * Recommends a tier based on expected usage.
 * Mirrors the Rust `PricingEngine::recommend_tier` method.
 */
export function recommendTier(params: {
  expectedWorkflows: number;
  expectedActionsPerDay: number;
  expectedTeamMembers: number;
  needsPolicyEngine: boolean;
  needsHitl: boolean;
}): SubscriptionTierName {
  const { expectedWorkflows, expectedActionsPerDay, expectedTeamMembers, needsPolicyEngine, needsHitl } = params;

  // On-Premise Enterprise: if they need self-hosted
  if (needsHitl && needsPolicyEngine && expectedTeamMembers > 100) {
    return 'on_premise_enterprise';
  }

  // Enterprise: unlimited or HITL
  if (needsHitl || expectedWorkflows > 25 || expectedActionsPerDay > 1000 || expectedTeamMembers > 15) {
    return 'enterprise';
  }

  // Business: advanced features
  if (expectedWorkflows > 5 || expectedActionsPerDay > 100 || expectedTeamMembers > 3 || needsPolicyEngine) {
    return 'business';
  }

  // Starter: basic usage
  return 'starter';
}
