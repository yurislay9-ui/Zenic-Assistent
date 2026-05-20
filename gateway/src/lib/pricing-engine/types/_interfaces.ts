// ─── Pricing Engine Interfaces ─────────────────────────────────────────
// Response types matching Rust JSON output.
// Extracted from pricing-engine/types.ts for modularity.

import type { SubscriptionTierName } from "./_enums";

// ═══════════════════════════════════════════════════════════════════════════
// Response Types (matching Rust JSON output)
// ═══════════════════════════════════════════════════════════════════════════

export interface TierInfo {
  name: string;
  display_name: string;
  monthly_price_usdt: number;
  annual_price_usdt: number;
  setup_fee_usdt: number;
  recommended_for: string;
  limits: TierLimitsInfo;
  payment_currency: string;
  payment_network: string;
}

export interface TierLimitsInfo {
  max_workflows: number;
  max_actions_per_day: number;
  max_policies: number;
  max_team_members: number;
  max_mcp_tools: number;
  max_approval_requests_per_day: number;
  max_playbooks: number;
  max_namespaces: number;
  max_simulations_per_month: number;
  audit_retention_days: number;
  trace_retention_days: number;
  overage_rate_usdt: number;
  sso_available: boolean;
  on_premise_available: boolean;
  custom_rbac: boolean;
  z3_solver: boolean;
}

export interface AddOnInfo {
  id: string;
  display_name: string;
  monthly_price_usdt: number;
  available_for_tiers: string[];
  payment_currency: string;
  payment_network: string;
}

export interface TrialConfigInfo {
  duration_days: number;
  requires_credit_card: boolean;
  granted_tier: string;
  max_trials_per_email: number;
  auto_convert: boolean;
  notification_schedule: number[];
  mandatory_for_all: boolean;
  trial_is_prerequisite: boolean;
}

export interface PricingCalc {
  tier: string;
  monthly_price_usdt: number;
  annual_price_usdt: number;
  setup_fee_usdt: number;
  add_ons_monthly_usdt: number;
  total_first_month_usdt: number;
  total_monthly_recurring_usdt: number;
  total_annual_usdt: number;
  overage_rate_usdt: number;
  payment_currency: string;
  payment_network: string;
}

export interface TierComp {
  tiers: PricingCalc[];
  recommended_tier: string;
  recommendation_reason: string;
  payment_currency: string;
  payment_network: string;
}

export interface FeatureCheck {
  feature: string;
  tier: string;
  available: boolean;
  minimum_tier: string | null;
  denial_reason: string | null;
}

export interface TierFeatureInfo {
  tier: string;
  display_name: string;
  features: Array<{ feature: string; available: boolean; minimum_tier: string | null }>;
  payment_currency: string;
  payment_network: string;
}

export interface UsageCheck {
  resource: string;
  allowed: boolean;
  current_usage: number;
  max_allowed: number;
  remaining: number;
  overage_charge_usdt: number;
  minimum_tier: string | null;
  feature_available: boolean;
  denial_reason: string | null;
}

export interface AddressValidation {
  address: string;
  valid: boolean;
  network: string;
  currency: string;
  reason: string;
}

export interface TrialSubscription {
  subscription: {
    id: string;
    tenant_id: string;
    tier: string;
    status: string;
    payment_method: string;
    billing_wallet: string;
    add_ons: string[];
    started_at: string;
    current_period_end: string;
    trial_ends_at: string | null;
    auto_renew: boolean;
    last_payment_tx_hash: string | null;
    cancelled_at: string | null;
    cancellation_reason: string | null;
  };
  trial_config: TrialConfigInfo;
  message: string;
  payment_required: boolean;
  payment_currency: string;
  payment_network: string;
}

export interface PaidSubscription {
  subscription: {
    id: string;
    tenant_id: string;
    tier: string;
    status: string;
    payment_method: string;
    billing_wallet: string;
    add_ons: string[];
    started_at: string;
    current_period_end: string;
    trial_ends_at: string | null;
    auto_renew: boolean;
    last_payment_tx_hash: string | null;
    cancelled_at: string | null;
    cancellation_reason: string | null;
  };
  payment_required: number;
  payment_currency: string;
  payment_network: string;
  breakdown: {
    monthly_usdt: number;
    setup_fee_usdt: number;
    first_payment_usdt: number;
  };
  message: string;
}

export interface PaymentVerificationMethodInfo {
  id: string;
  display_name: string;
  description: string;
  currency: string;
  network: string;
}

export interface ManualPaymentVerification {
  payment_id: string;
  subscription_id: string;
  amount_usdt: number;
  wallet_from: string;
  wallet_to: string;
  tx_hash: string | null;
  verification_method: import("./_enums").PaymentVerificationMethod;
  status: import("./_enums").ManualPaymentStatus;
  admin_notes: string | null;
  confirmed_by: string | null;
  confirmed_at: string | null;
  created_at: string;
}

export interface ManualPaymentRequest {
  payment_request: ManualPaymentVerification;
  instructions: {
    step1: string;
    step2: string;
    step3: string;
    step4: string;
  };
  platform_wallet: string;
  amount_usdt: number;
  payment_currency: string;
  payment_network: string;
  estimated_confirmation_time: string;
}
