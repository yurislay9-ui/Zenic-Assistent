// ─── Zenic-Agents v3 — Pricing Engine Barrel Export ────────────────────
// USDT TRC20 ONLY. All pricing engine exports in one place.

// ─── Types ────────────────────────────────────────────────────────────────
export type {
  SubscriptionTierName,
  SubscriptionStatus,
  PaymentMethod,
  PaymentStatus,
  AddOnId,
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
  PaymentVerificationMethod,
  ManualPaymentStatus,
  PaymentVerificationMethodInfo,
  ManualPaymentVerification,
  ManualPaymentRequest,
} from "./types";

export {
  SubscriptionTierName as SubscriptionTierNameConst,
  SubscriptionStatus as SubscriptionStatusConst,
  PaymentMethod as PaymentMethodConst,
  PaymentStatus as PaymentStatusConst,
  AddOnId as AddOnIdConst,
  PaymentVerificationMethod as PaymentVerificationMethodConst,
  ManualPaymentStatus as ManualPaymentStatusConst,
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
} from "./types";

// ─── WASM Bridge ──────────────────────────────────────────────────────────
export {
  initWasm,
  isWasmActive,
  getWasmLoadError,
  resetWasm,
  engineVersion,
  getAllTiers,
  getPaidTiers,
  getAddOns,
  getTrialConfig,
  calculatePricing,
  compareTiers,
  checkFeature,
  getTierFeatures,
  checkUsage,
  getTierLimits,
  validateTrc20Address,
  createTrialSubscription,
  convertTrialToPaid,
  getPaymentVerificationMethods,
  isTrialMandatory,
  createManualPaymentRequest,
  confirmManualPayment,
} from "./wasm-bridge";

// ─── Feature Gate ─────────────────────────────────────────────────────────
export {
  getSubscriptionForTenant,
  checkFeatureAccess,
  checkUsageLimit,
  enforceTierAccess,
  requireFeature,
} from "./feature-gate";

// ─── Saga Pattern ────────────────────────────────────────────────────────
export type {
  SagaTypeName,
  SagaStatusName,
  SagaStepStatusName,
  SagaStepResult,
  SagaOrchestratorResult,
} from "./saga";

export {
  SagaTypeName as SagaTypeNameConst,
  SagaStatusName as SagaStatusNameConst,
  SagaStepStatusName as SagaStepStatusNameConst,
  executeSaga,
  resumeSaga,
  getSagaStatus,
  getSagasForTenant,
  getSagaTypes,
  getSagaDefinition,
  validateUpgradePath,
  validateDowngradePath,
  calculateProration,
} from "./saga";
