/**
 * Zenic-Agents Subscription Type System
 *
 * Re-exports all types, constants, and helpers from sub-modules.
 * All payments USDT TRC20 only.
 */

// ─── Core types and constants ───
export type { SubscriptionTierName, SubscriptionStatus } from "./_core";
export {
  TIER_RANK,
  TIER_PRICES,
  TIER_DISPLAY_NAMES,
  ACTIVE_STATUSES,
  canTransitionTo,
  isSubscriptionActive,
  getTierLimits,
  getMemoryConfig,
  canUpgrade,
} from "./_core";
export type { TierLimits, MemoryTierConfig } from "./_core";

// ─── Plans, features, and helpers ───
export type {
  FeatureGateDefinition,
  AddOnDefinition,
  PaymentMethod,
  PaymentStatus,
  UsdtPayment,
  Trial,
  Subscription,
  UsageType,
  UsageRecord,
} from "./_plan";
export {
  FEATURE_GATES,
  ADD_ONS,
  isFeatureAvailable,
  calculateFirstPayment,
  calculateUpgradeProration,
  getFeaturesForTier,
  getUnavailableFeaturesForTier,
  recommendTier,
} from "./_plan";
