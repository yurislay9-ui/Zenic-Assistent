// ─── WASM Bridge — Internal Types ────────────────────────────────────────────
// Re-exports pricing-engine domain types and defines the WASM module interface
// used internally by the loader, fallback, and executor modules.

// ═══════════════════════════════════════════════════════════════════════════
// Re-exports from parent types module
// ═══════════════════════════════════════════════════════════════════════════

export type {
  SubscriptionTierName,
  FeatureName,
  TierInfo,
  TierLimitsInfo,
  AddOnInfo,
  TrialConfigInfo,
  PricingCalc,
  TierComp,
  FeatureCheck,
  TierFeatureInfo,
  UsageCheck,
  AddressValidation,
  TrialSubscription,
  PaidSubscription,
  PaymentVerificationMethodInfo,
  ManualPaymentRequest,
} from "../types";

export {
  SubscriptionTierName as TierName,
  TIER_PRICES_USDT,
  ADDON_PRICES_USDT,
  ADDON_DISPLAY_NAMES,
  ADDON_AVAILABLE_TIERS,
  TRIAL_CONFIG,
  PAYMENT_CURRENCY,
  PAYMENT_NETWORK,
  TIER_LIMITS,
  TIER_DISPLAY_NAMES,
  TIER_RECOMMENDED_FOR,
  FEATURE_TIER_MAP,
  TIER_ORDER,
  PAID_TIER_NAMES,
  ALL_TIER_NAMES,
} from "../types";

// ═══════════════════════════════════════════════════════════════════════════
// WASM Module Interface
// ═══════════════════════════════════════════════════════════════════════════

export interface WasmModule {
  engine_version(): string;
  get_all_tiers(): string;
  get_paid_tiers(): string;
  get_add_ons(): string;
  get_trial_config(): string;
  calculate_pricing(tier_name: string, add_ons_json: string): string;
  compare_tiers(estimated_actions_per_month: number, add_ons_json: string): string;
  check_feature(tier_name: string, feature_name: string): string;
  get_tier_features(tier_name: string): string;
  check_usage(tier_name: string, resource: string, current_usage: number): string;
  get_tier_limits(tier_name: string): string;
  validate_trc20_address(address: string): string;
  create_trial_subscription(tenant_id: string, email: string): string;
  convert_trial_to_paid(tenant_id: string, tier_name: string, wallet_address: string): string;
  get_payment_verification_methods(): string;
  is_trial_mandatory(): string;
  create_manual_payment_request(subscription_id: string, amount_usdt: number, wallet_from: string, platform_wallet: string): string;
  confirm_manual_payment(payment_id: string, tx_hash: string, confirmed_by: string): string;
}
