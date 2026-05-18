// ─── Zenic-Agents v3 — WASM Bridge Public API ────────────────────────
// Split from wasm-bridge.ts — WASM-first with TS fallback public functions

import type {
  TierInfo,
  AddOnInfo,
  TrialConfigInfo,
  PricingCalc,
  TierComp,
  FeatureCheck,
  TierFeatureInfo,
  UsageCheck,
  TierLimitsInfo,
  AddressValidation,
  TrialSubscription,
  PaidSubscription,
  PaymentVerificationMethodInfo,
  ManualPaymentRequest,
} from "../types";
import { getWasmModule } from "./_wasm-loader";
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
} from "./_ts-fallback-subscription";

export function engineVersion(): string {
  if (getWasmModule()) { try { return getWasmModule()!.engine_version(); } catch { return tsEngineVersion(); } }
  return tsEngineVersion();
}

export function getAllTiers(): TierInfo[] {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.get_all_tiers()) as TierInfo[]; } catch { return tsGetAllTiers(); } }
  return tsGetAllTiers();
}

export function getPaidTiers(): TierInfo[] {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.get_paid_tiers()) as TierInfo[]; } catch { return tsGetPaidTiers(); } }
  return tsGetPaidTiers();
}

export function getAddOns(): AddOnInfo[] {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.get_add_ons()) as AddOnInfo[]; } catch { return tsGetAddOns(); } }
  return tsGetAddOns();
}

export function getTrialConfig(): TrialConfigInfo {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.get_trial_config()) as TrialConfigInfo; } catch { return tsGetTrialConfig(); } }
  return tsGetTrialConfig();
}

export function calculatePricing(tierName: string, addOns?: string[]): PricingCalc {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.calculate_pricing(tierName, JSON.stringify(addOns ?? []))) as PricingCalc; } catch { return tsCalculatePricing(tierName, addOns); } }
  return tsCalculatePricing(tierName, addOns);
}

export function compareTiers(estimatedActions: number, addOns?: string[]): TierComp {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.compare_tiers(estimatedActions, JSON.stringify(addOns ?? []))) as TierComp; } catch { return tsCompareTiers(estimatedActions, addOns); } }
  return tsCompareTiers(estimatedActions, addOns);
}

export function checkFeature(tierName: string, featureName: string): FeatureCheck {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.check_feature(tierName, featureName)) as FeatureCheck; } catch { return tsCheckFeature(tierName, featureName); } }
  return tsCheckFeature(tierName, featureName);
}

export function getTierFeatures(tierName: string): TierFeatureInfo {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.get_tier_features(tierName)) as TierFeatureInfo; } catch { return tsGetTierFeatures(tierName); } }
  return tsGetTierFeatures(tierName);
}

export function checkUsage(tierName: string, resource: string, currentUsage: number): UsageCheck {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.check_usage(tierName, resource, currentUsage)) as UsageCheck; } catch { return tsCheckUsage(tierName, resource, currentUsage); } }
  return tsCheckUsage(tierName, resource, currentUsage);
}

export function getTierLimits(tierName: string): TierLimitsInfo {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.get_tier_limits(tierName)) as TierLimitsInfo; } catch { return tsGetTierLimits(tierName); } }
  return tsGetTierLimits(tierName);
}

export function validateTrc20Address(address: string): AddressValidation {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.validate_trc20_address(address)) as AddressValidation; } catch { return tsValidateTrc20Address(address); } }
  return tsValidateTrc20Address(address);
}

export function createTrialSubscription(tenantId: string, email: string): TrialSubscription {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.create_trial_subscription(tenantId, email)) as TrialSubscription; } catch { return tsCreateTrialSubscription(tenantId, email); } }
  return tsCreateTrialSubscription(tenantId, email);
}

export function convertTrialToPaid(tenantId: string, tierName: string, walletAddress: string): PaidSubscription {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.convert_trial_to_paid(tenantId, tierName, walletAddress)) as PaidSubscription; } catch { return tsConvertTrialToPaid(tenantId, tierName, walletAddress); } }
  return tsConvertTrialToPaid(tenantId, tierName, walletAddress);
}

export function getPaymentVerificationMethods(): PaymentVerificationMethodInfo[] {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.get_payment_verification_methods()) as PaymentVerificationMethodInfo[]; } catch { return tsGetPaymentVerificationMethods(); } }
  return tsGetPaymentVerificationMethods();
}

export function isTrialMandatory() {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.is_trial_mandatory()); } catch { return tsIsTrialMandatory(); } }
  return tsIsTrialMandatory();
}

export function createManualPaymentRequest(subscriptionId: string, amountUsdt: number, walletFrom: string, platformWallet: string): ManualPaymentRequest {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.create_manual_payment_request(subscriptionId, amountUsdt, walletFrom, platformWallet)) as ManualPaymentRequest; } catch { return tsCreateManualPaymentRequest(subscriptionId, amountUsdt, walletFrom, platformWallet); } }
  return tsCreateManualPaymentRequest(subscriptionId, amountUsdt, walletFrom, platformWallet);
}

export function confirmManualPayment(paymentId: string, txHash: string, confirmedBy: string) {
  if (getWasmModule()) { try { return JSON.parse(getWasmModule()!.confirm_manual_payment(paymentId, txHash, confirmedBy)); } catch { return tsConfirmManualPayment(paymentId, txHash, confirmedBy); } }
  return tsConfirmManualPayment(paymentId, txHash, confirmedBy);
}
