// ─── WASM Bridge — Executor ──────────────────────────────────────────────────
// Public API — WASM-first with TypeScript fallback.
// Every function attempts to call the WASM engine first; if WASM is
// unavailable or the call throws, it falls back to the pure TS implementation.

import type {
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

import { wasmModule } from "./_loader";

import {
  tsEngineVersion,
  tsGetAllTiers,
  tsGetPaidTiers,
  tsGetAddOns,
  tsGetTrialConfig,
  tsCalculatePricing,
  tsCompareTiers,
  tsCheckFeature,
  tsGetTierFeatures,
  tsCheckUsage,
  tsGetTierLimits,
} from "./_ts-fallback-core";

import {
  tsValidateTrc20Address,
  tsCreateTrialSubscription,
  tsConvertTrialToPaid,
  tsGetPaymentVerificationMethods,
  tsIsTrialMandatory,
  tsCreateManualPaymentRequest,
  tsConfirmManualPayment,
} from "./_ts-fallback-payment";

// ═══════════════════════════════════════════════════════════════════════════
// Public API — WASM-first with TS fallback
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Get the engine version.
 * WASM-first, TS fallback.
 */
export function engineVersion(): string {
  if (wasmModule) {
    try {
      return wasmModule.engine_version();
    } catch {
      return tsEngineVersion();
    }
  }
  return tsEngineVersion();
}

/**
 * Get all subscription tiers (including trial).
 * WASM-first, TS fallback.
 */
export function getAllTiers(): TierInfo[] {
  if (wasmModule) {
    try {
      const raw = wasmModule.get_all_tiers();
      return JSON.parse(raw) as TierInfo[];
    } catch {
      return tsGetAllTiers();
    }
  }
  return tsGetAllTiers();
}

/**
 * Get paid subscription tiers only (excludes trial).
 * WASM-first, TS fallback.
 */
export function getPaidTiers(): TierInfo[] {
  if (wasmModule) {
    try {
      const raw = wasmModule.get_paid_tiers();
      return JSON.parse(raw) as TierInfo[];
    } catch {
      return tsGetPaidTiers();
    }
  }
  return tsGetPaidTiers();
}

/**
 * Get all available add-ons.
 * WASM-first, TS fallback.
 */
export function getAddOns(): AddOnInfo[] {
  if (wasmModule) {
    try {
      const raw = wasmModule.get_add_ons();
      return JSON.parse(raw) as AddOnInfo[];
    } catch {
      return tsGetAddOns();
    }
  }
  return tsGetAddOns();
}

/**
 * Get trial configuration.
 * WASM-first, TS fallback.
 */
export function getTrialConfig(): TrialConfigInfo {
  if (wasmModule) {
    try {
      const raw = wasmModule.get_trial_config();
      return JSON.parse(raw) as TrialConfigInfo;
    } catch {
      return tsGetTrialConfig();
    }
  }
  return tsGetTrialConfig();
}

/**
 * Calculate pricing for a tier with optional add-ons.
 * WASM-first, TS fallback.
 */
export function calculatePricing(tierName: string, addOns?: string[]): PricingCalc {
  if (wasmModule) {
    try {
      const raw = wasmModule.calculate_pricing(tierName, JSON.stringify(addOns ?? []));
      return JSON.parse(raw) as PricingCalc;
    } catch {
      return tsCalculatePricing(tierName, addOns);
    }
  }
  return tsCalculatePricing(tierName, addOns);
}

/**
 * Compare all tiers for a given estimated action count.
 * WASM-first, TS fallback.
 */
export function compareTiers(estimatedActions: number, addOns?: string[]): TierComp {
  if (wasmModule) {
    try {
      const raw = wasmModule.compare_tiers(estimatedActions, JSON.stringify(addOns ?? []));
      return JSON.parse(raw) as TierComp;
    } catch {
      return tsCompareTiers(estimatedActions, addOns);
    }
  }
  return tsCompareTiers(estimatedActions, addOns);
}

/**
 * Check if a feature is available for a tier.
 * WASM-first, TS fallback.
 */
export function checkFeature(tierName: string, featureName: string): FeatureCheck {
  if (wasmModule) {
    try {
      const raw = wasmModule.check_feature(tierName, featureName);
      return JSON.parse(raw) as FeatureCheck;
    } catch {
      return tsCheckFeature(tierName, featureName);
    }
  }
  return tsCheckFeature(tierName, featureName);
}

/**
 * Get all features for a tier with availability info.
 * WASM-first, TS fallback.
 */
export function getTierFeatures(tierName: string): TierFeatureInfo {
  if (wasmModule) {
    try {
      const raw = wasmModule.get_tier_features(tierName);
      return JSON.parse(raw) as TierFeatureInfo;
    } catch {
      return tsGetTierFeatures(tierName);
    }
  }
  return tsGetTierFeatures(tierName);
}

/**
 * Check usage against tier limits.
 * WASM-first, TS fallback.
 */
export function checkUsage(tierName: string, resource: string, currentUsage: number): UsageCheck {
  if (wasmModule) {
    try {
      const raw = wasmModule.check_usage(tierName, resource, currentUsage);
      return JSON.parse(raw) as UsageCheck;
    } catch {
      return tsCheckUsage(tierName, resource, currentUsage);
    }
  }
  return tsCheckUsage(tierName, resource, currentUsage);
}

/**
 * Get tier limits.
 * WASM-first, TS fallback.
 */
export function getTierLimits(tierName: string): TierLimitsInfo {
  if (wasmModule) {
    try {
      const raw = wasmModule.get_tier_limits(tierName);
      return JSON.parse(raw) as TierLimitsInfo;
    } catch {
      return tsGetTierLimits(tierName);
    }
  }
  return tsGetTierLimits(tierName);
}

/**
 * Validate a TRC20 wallet address.
 * WASM-first, TS fallback.
 */
export function validateTrc20Address(address: string): AddressValidation {
  if (wasmModule) {
    try {
      const raw = wasmModule.validate_trc20_address(address);
      return JSON.parse(raw) as AddressValidation;
    } catch {
      return tsValidateTrc20Address(address);
    }
  }
  return tsValidateTrc20Address(address);
}

/**
 * Create a trial subscription.
 * WASM-first, TS fallback.
 */
export function createTrialSubscription(tenantId: string, email: string): TrialSubscription {
  if (wasmModule) {
    try {
      const raw = wasmModule.create_trial_subscription(tenantId, email);
      return JSON.parse(raw) as TrialSubscription;
    } catch {
      return tsCreateTrialSubscription(tenantId, email);
    }
  }
  return tsCreateTrialSubscription(tenantId, email);
}

/**
 * Convert a trial subscription to a paid one.
 * USDT TRC20 payment required.
 * WASM-first, TS fallback.
 */
export function convertTrialToPaid(tenantId: string, tierName: string, walletAddress: string): PaidSubscription {
  if (wasmModule) {
    try {
      const raw = wasmModule.convert_trial_to_paid(tenantId, tierName, walletAddress);
      return JSON.parse(raw) as PaidSubscription;
    } catch {
      return tsConvertTrialToPaid(tenantId, tierName, walletAddress);
    }
  }
  return tsConvertTrialToPaid(tenantId, tierName, walletAddress);
}

/**
 * Get available payment verification methods.
 * WASM-first, TS fallback.
 */
export function getPaymentVerificationMethods(): PaymentVerificationMethodInfo[] {
  if (wasmModule) {
    try {
      const raw = wasmModule.get_payment_verification_methods();
      return JSON.parse(raw) as PaymentVerificationMethodInfo[];
    } catch {
      return tsGetPaymentVerificationMethods();
    }
  }
  return tsGetPaymentVerificationMethods();
}

/**
 * Check if the 14-day trial is mandatory for all users.
 * WASM-first, TS fallback.
 */
export function isTrialMandatory() {
  if (wasmModule) {
    try {
      const raw = wasmModule.is_trial_mandatory();
      return JSON.parse(raw);
    } catch {
      return tsIsTrialMandatory();
    }
  }
  return tsIsTrialMandatory();
}

/**
 * Create a manual payment request for USDT TRC20.
 * WASM-first, TS fallback.
 */
export function createManualPaymentRequest(subscriptionId: string, amountUsdt: number, walletFrom: string, platformWallet: string): ManualPaymentRequest {
  if (wasmModule) {
    try {
      const raw = wasmModule.create_manual_payment_request(subscriptionId, amountUsdt, walletFrom, platformWallet);
      return JSON.parse(raw) as ManualPaymentRequest;
    } catch {
      return tsCreateManualPaymentRequest(subscriptionId, amountUsdt, walletFrom, platformWallet);
    }
  }
  return tsCreateManualPaymentRequest(subscriptionId, amountUsdt, walletFrom, platformWallet);
}

/**
 * Confirm a manual payment with tx hash.
 * USDT TRC20 only, manual/semi-manual verification.
 * WASM-first, TS fallback.
 */
export function confirmManualPayment(paymentId: string, txHash: string, confirmedBy: string) {
  if (wasmModule) {
    try {
      const raw = wasmModule.confirm_manual_payment(paymentId, txHash, confirmedBy);
      return JSON.parse(raw);
    } catch {
      return tsConfirmManualPayment(paymentId, txHash, confirmedBy);
    }
  }
  return tsConfirmManualPayment(paymentId, txHash, confirmedBy);
}
