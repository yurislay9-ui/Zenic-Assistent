// ─── WASM Bridge — Public API ────────────────────────────────────────────────
// USDT TRC20 ONLY. All prices in USDT, TRC20 network only.
//
// This module provides a typed TypeScript API over the compiled Rust → WASM
// pricing engine. It attempts to load the WASM binary first; if that fails
// (e.g., in Edge runtime, SSR without WASM support, or before initialization),
// it transparently falls back to a pure TypeScript implementation that mirrors
// the EXACT same logic as the Rust engine — same tier prices, same feature
// gates, same limits.
//
// Re-exports every symbol that the original wasm-bridge.ts exported, ensuring
// 100 % backward compatibility for all importers.

// ─── Loader ──────────────────────────────────────────────────────────────────
export { initWasm, isWasmActive, getWasmLoadError, resetWasm } from "./_loader";

// ─── Executor (WASM-first, TS fallback) ──────────────────────────────────────
export {
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
} from "./_executor";

// ─── Types (re-exported for convenience) ─────────────────────────────────────
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
} from "./types";
