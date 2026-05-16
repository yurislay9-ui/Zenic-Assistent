// ─── Zenic-Agents v3 — WASM Bridge for Rust Pricing Engine ─────────────
// USDT TRC20 ONLY. All prices in USDT, TRC20 network only.
//
// This module provides a typed TypeScript API over the compiled Rust → WASM
// pricing engine. It attempts to load the WASM binary first; if that fails
// (e.g., in Edge runtime, SSR without WASM support, or before initialization),
// it transparently falls back to a pure TypeScript implementation that mirrors
// the EXACT same logic as the Rust engine — same tier prices, same feature
// gates, same limits.

import type {
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

import {
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
} from "./types";

// ═══════════════════════════════════════════════════════════════════════════
// WASM Module Interface
// ═══════════════════════════════════════════════════════════════════════════

interface WasmModule {
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

// ═══════════════════════════════════════════════════════════════════════════
// WASM Loading State
// ═══════════════════════════════════════════════════════════════════════════

let wasmModule: WasmModule | null = null;
let wasmLoadAttempted = false;
let wasmLoadError: string | null = null;

/**
 * Attempt to load the WASM module from the compiled Rust package.
 * Returns true if WASM was loaded successfully, false if using TS fallback.
 */
export async function initWasm(): Promise<boolean> {
  if (wasmModule) return true;
  if (wasmLoadAttempted) return false;

  wasmLoadAttempted = true;

  try {
    // Dynamic import of the WASM module from the Rust engine package
    const wasmPkg = (await import("../../../rust-engine/pkg/zenic_pricing_engine.js")) as unknown as WasmModule;
    wasmModule = wasmPkg;
    wasmLoadError = null;
    return true;
  } catch (err) {
    wasmLoadError = err instanceof Error ? err.message : String(err);
    wasmModule = null;
    return false;
  }
}

/**
 * Returns whether the WASM engine is currently active.
 */
export function isWasmActive(): boolean {
  return wasmModule !== null;
}

/**
 * Returns the WASM load error if the TS fallback is being used.
 */
export function getWasmLoadError(): string | null {
  return wasmLoadError;
}

/**
 * Reset WASM state (useful for testing or re-initialization).
 */
export function resetWasm(): void {
  wasmModule = null;
  wasmLoadAttempted = false;
  wasmLoadError = null;
}

// ═══════════════════════════════════════════════════════════════════════════
// TypeScript Fallback Implementation
// Mirrors the EXACT same logic as the Rust engine.
// ═══════════════════════════════════════════════════════════════════════════

function resolveTierName(tier: string): SubscriptionTierName | null {
  const lower = tier.toLowerCase();
  if (lower === "onpremise" || lower === "on-premise") return TierName.ON_PREMISE_ENTERPRISE;
  const found = ALL_TIER_NAMES.find(t => t === lower);
  return found ?? null;
}

function tsFeatureAvailable(tierName: SubscriptionTierName, feature: FeatureName): boolean {
  const allowedTiers = FEATURE_TIER_MAP[feature];
  if (!allowedTiers) return false;
  return allowedTiers.includes(tierName);
}

function tsMinimumTier(feature: FeatureName): string | null {
  const allowedTiers = FEATURE_TIER_MAP[feature];
  if (!allowedTiers || allowedTiers.length === 0) return null;
  // Return the lowest tier in the upgrade path
  for (const tier of TIER_ORDER) {
    if (allowedTiers.includes(tier)) return tier;
  }
  // Check trial separately
  if (allowedTiers.includes(TierName.TRIAL)) return TierName.TRIAL;
  return allowedTiers[0] ?? null;
}

function tsEngineVersion(): string {
  return "3.0.0";
}

function tsGetAllTiers(): TierInfo[] {
  return ALL_TIER_NAMES.map(name => {
    const prices = TIER_PRICES_USDT[name];
    const limits = TIER_LIMITS[name];
    return {
      name,
      display_name: TIER_DISPLAY_NAMES[name],
      monthly_price_usdt: prices.monthly,
      annual_price_usdt: prices.annual,
      setup_fee_usdt: prices.setup,
      recommended_for: TIER_RECOMMENDED_FOR[name],
      limits,
      payment_currency: PAYMENT_CURRENCY,
      payment_network: PAYMENT_NETWORK,
    };
  });
}

function tsGetPaidTiers(): TierInfo[] {
  return PAID_TIER_NAMES.map(name => {
    const prices = TIER_PRICES_USDT[name];
    const limits = TIER_LIMITS[name];
    return {
      name,
      display_name: TIER_DISPLAY_NAMES[name],
      monthly_price_usdt: prices.monthly,
      annual_price_usdt: prices.annual,
      setup_fee_usdt: prices.setup,
      recommended_for: TIER_RECOMMENDED_FOR[name],
      limits,
      payment_currency: PAYMENT_CURRENCY,
      payment_network: PAYMENT_NETWORK,
    };
  });
}

function tsGetAddOns(): AddOnInfo[] {
  return Object.keys(ADDON_PRICES_USDT).map(id => ({
    id,
    display_name: ADDON_DISPLAY_NAMES[id] ?? id,
    monthly_price_usdt: ADDON_PRICES_USDT[id],
    available_for_tiers: ADDON_AVAILABLE_TIERS[id] ?? [],
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
  }));
}

function tsGetTrialConfig(): TrialConfigInfo {
  return TRIAL_CONFIG;
}

function tsCalculatePricing(tierName: string, addOns?: string[]): PricingCalc {
  const resolved = resolveTierName(tierName);
  if (!resolved) {
    return {
      tier: tierName,
      monthly_price_usdt: 0,
      annual_price_usdt: 0,
      setup_fee_usdt: 0,
      add_ons_monthly_usdt: 0,
      total_first_month_usdt: 0,
      total_monthly_recurring_usdt: 0,
      total_annual_usdt: 0,
      overage_rate_usdt: 0,
      payment_currency: PAYMENT_CURRENCY,
      payment_network: PAYMENT_NETWORK,
    };
  }

  const prices = TIER_PRICES_USDT[resolved];
  const limits = TIER_LIMITS[resolved];
  const addOnsMonthly = (addOns ?? []).reduce((sum, id) => sum + (ADDON_PRICES_USDT[id] ?? 0), 0);
  const monthly = prices.monthly;
  const annual = prices.annual;
  const setup = prices.setup;

  return {
    tier: resolved,
    monthly_price_usdt: monthly,
    annual_price_usdt: annual,
    setup_fee_usdt: setup,
    add_ons_monthly_usdt: addOnsMonthly,
    total_first_month_usdt: monthly + setup + addOnsMonthly,
    total_monthly_recurring_usdt: monthly + addOnsMonthly,
    total_annual_usdt: annual + setup + (addOnsMonthly * 12),
    overage_rate_usdt: limits.overage_rate_usdt,
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
  };
}

function tsCompareTiers(estimatedActions: number, addOns?: string[]): TierComp {
  const addOnsMonthly = (addOns ?? []).reduce((sum, id) => sum + (ADDON_PRICES_USDT[id] ?? 0), 0);

  const tiers: PricingCalc[] = PAID_TIER_NAMES.map(name => {
    const prices = TIER_PRICES_USDT[name];
    const limits = TIER_LIMITS[name];
    const monthly = prices.monthly;
    return {
      tier: name,
      monthly_price_usdt: monthly,
      annual_price_usdt: prices.annual,
      setup_fee_usdt: prices.setup,
      add_ons_monthly_usdt: addOnsMonthly,
      total_first_month_usdt: monthly + prices.setup + addOnsMonthly,
      total_monthly_recurring_usdt: monthly + addOnsMonthly,
      total_annual_usdt: prices.annual + prices.setup + (addOnsMonthly * 12),
      overage_rate_usdt: limits.overage_rate_usdt,
      payment_currency: PAYMENT_CURRENCY,
      payment_network: PAYMENT_NETWORK,
    };
  });

  let recommended: string;
  let reason: string;

  if (estimatedActions < 500) {
    recommended = TierName.STARTER;
    reason = `Con ${estimatedActions} acciones/mes, Starter ofrece el mejor valor.`;
  } else if (estimatedActions <= 5000) {
    recommended = TierName.BUSINESS;
    reason = `Con ${estimatedActions} acciones/mes, Business es la elecci\u00f3n \u00f3ptima.`;
  } else if (estimatedActions <= 50000) {
    recommended = TierName.ENTERPRISE;
    reason = `Con ${estimatedActions} acciones/mes, Enterprise maximiza el ROI.`;
  } else {
    recommended = TierName.ON_PREMISE_ENTERPRISE;
    reason = `Con ${estimatedActions} acciones/mes, On-Premise Enterprise es la soluci\u00f3n.`;
  }

  return {
    tiers,
    recommended_tier: recommended,
    recommendation_reason: reason,
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
  };
}

function tsCheckFeature(tierName: string, featureName: string): FeatureCheck {
  const resolved = resolveTierName(tierName);
  if (!resolved) {
    return {
      feature: featureName,
      tier: tierName,
      available: false,
      minimum_tier: null,
      denial_reason: `Unknown tier: ${tierName}`,
    };
  }

  const feature = featureName as FeatureName;
  const allowedTiers = FEATURE_TIER_MAP[feature];
  if (!allowedTiers) {
    return {
      feature: featureName,
      tier: tierName,
      available: false,
      minimum_tier: null,
      denial_reason: `Unknown feature: ${featureName}`,
    };
  }

  const available = tsFeatureAvailable(resolved, feature);
  const minTier = tsMinimumTier(feature);

  return {
    feature: featureName,
    tier: tierName,
    available,
    minimum_tier: minTier,
    denial_reason: available
      ? null
      : `Feature '${featureName}' requires upgrade from '${TIER_DISPLAY_NAMES[resolved]}'`,
  };
}

function tsGetTierFeatures(tierName: string): TierFeatureInfo {
  const resolved = resolveTierName(tierName);
  if (!resolved) {
    return {
      tier: tierName,
      display_name: tierName,
      features: [],
      payment_currency: PAYMENT_CURRENCY,
      payment_network: PAYMENT_NETWORK,
    };
  }

  const featureNames = Object.keys(FEATURE_TIER_MAP) as FeatureName[];
  const features = featureNames.map(name => {
    const available = tsFeatureAvailable(resolved, name);
    const minTier = tsMinimumTier(name);
    return {
      feature: name,
      available,
      minimum_tier: minTier,
    };
  });

  return {
    tier: tierName,
    display_name: TIER_DISPLAY_NAMES[resolved],
    features,
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
  };
}

function tsCheckUsage(tierName: string, resource: string, currentUsage: number): UsageCheck {
  const resolved = resolveTierName(tierName);
  if (!resolved) {
    return {
      resource,
      allowed: false,
      current_usage: currentUsage,
      max_allowed: 0,
      remaining: 0,
      overage_charge_usdt: 0,
      minimum_tier: null,
      feature_available: false,
      denial_reason: `Unknown tier: ${tierName}`,
    };
  }

  const limits = TIER_LIMITS[resolved];
  const resourceMap: Record<string, { max: number; overageRate: number }> = {
    workflows: { max: limits.max_workflows, overageRate: 0 },
    actions_per_day: { max: limits.max_actions_per_day, overageRate: limits.overage_rate_usdt },
    policies: { max: limits.max_policies, overageRate: 0 },
    team_members: { max: limits.max_team_members, overageRate: 0 },
    mcp_tools: { max: limits.max_mcp_tools, overageRate: 0 },
    approval_requests_per_day: { max: limits.max_approval_requests_per_day, overageRate: limits.overage_rate_usdt },
    playbooks: { max: limits.max_playbooks, overageRate: 0 },
    namespaces: { max: limits.max_namespaces, overageRate: 0 },
    simulations_per_month: { max: limits.max_simulations_per_month, overageRate: 0 },
  };

  const entry = resourceMap[resource];
  if (!entry) {
    return {
      resource,
      allowed: false,
      current_usage: currentUsage,
      max_allowed: 0,
      remaining: 0,
      overage_charge_usdt: 0,
      minimum_tier: null,
      feature_available: false,
      denial_reason: `Unknown resource: ${resource}`,
    };
  }

  const max = entry.max;
  const overageRate = entry.overageRate;
  const allowed = max === 0 || currentUsage <= max;
  const remaining = max === 0 ? 0 : Math.max(0, max - currentUsage);
  const overage = max > 0 && currentUsage > max ? (currentUsage - max) * overageRate : 0;
  const denialReason = !allowed && max > 0
    ? `Usage ${currentUsage} exceeds limit ${max} for '${resource}' on ${TIER_DISPLAY_NAMES[resolved]} tier. Upgrade required.`
    : null;

  return {
    resource,
    allowed,
    current_usage: currentUsage,
    max_allowed: max,
    remaining,
    overage_charge_usdt: overage,
    minimum_tier: null,
    feature_available: allowed,
    denial_reason: denialReason,
  };
}

function tsGetTierLimits(tierName: string): TierLimitsInfo {
  const resolved = resolveTierName(tierName);
  if (!resolved) {
    return TIER_LIMITS[TierName.STARTER];
  }
  return TIER_LIMITS[resolved];
}

function tsValidateTrc20Address(address: string): AddressValidation {
  const valid = address.startsWith("T") && address.length === 34 && address.slice(1).split("").every(c => /[A-Za-z0-9]/.test(c));
  return {
    address,
    valid,
    network: PAYMENT_NETWORK,
    currency: PAYMENT_CURRENCY,
    reason: valid
      ? "Valid TRC20 address format"
      : "TRC20 address must start with 'T' and be 34 characters alphanumeric",
  };
}

function tsCreateTrialSubscription(tenantId: string, email: string): TrialSubscription {
  const config = TRIAL_CONFIG;
  const now = new Date();
  const endDate = new Date(now.getTime() + config.duration_days * 24 * 60 * 60 * 1000);

  return {
    subscription: {
      id: `sub_trial_${simpleHash(tenantId + ":" + email)}`,
      tenant_id: tenantId,
      tier: TierName.TRIAL,
      status: "trial",
      payment_method: "UsdtTrc20",
      billing_wallet: "",
      add_ons: [],
      started_at: now.toISOString(),
      current_period_end: endDate.toISOString(),
      trial_ends_at: endDate.toISOString(),
      auto_renew: false,
      last_payment_tx_hash: null,
      cancelled_at: null,
      cancellation_reason: null,
    },
    trial_config: config,
    message: `Trial de ${config.duration_days} d\u00edas activado. Acceso completo al Plan Business.`,
    payment_required: false,
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
  };
}

function tsConvertTrialToPaid(tenantId: string, tierName: string, walletAddress: string): PaidSubscription {
  const resolved = resolveTierName(tierName);
  if (!resolved || resolved === TierName.TRIAL) {
    return {
      subscription: {
        id: "",
        tenant_id: tenantId,
        tier: tierName,
        status: "active",
        payment_method: "UsdtTrc20",
        billing_wallet: walletAddress,
        add_ons: [],
        started_at: new Date().toISOString(),
        current_period_end: new Date().toISOString(),
        trial_ends_at: null,
        auto_renew: true,
        last_payment_tx_hash: null,
        cancelled_at: null,
        cancellation_reason: null,
      },
      payment_required: 0,
      payment_currency: PAYMENT_CURRENCY,
      payment_network: PAYMENT_NETWORK,
      breakdown: { monthly_usdt: 0, setup_fee_usdt: 0, first_payment_usdt: 0 },
      message: "Must convert to a paid tier",
    };
  }

  const walletValid = walletAddress.startsWith("T") && walletAddress.length === 34;
  if (!walletValid) {
    return {
      subscription: {
        id: "",
        tenant_id: tenantId,
        tier: resolved,
        status: "active",
        payment_method: "UsdtTrc20",
        billing_wallet: walletAddress,
        add_ons: [],
        started_at: new Date().toISOString(),
        current_period_end: new Date().toISOString(),
        trial_ends_at: null,
        auto_renew: true,
        last_payment_tx_hash: null,
        cancelled_at: null,
        cancellation_reason: null,
      },
      payment_required: 0,
      payment_currency: PAYMENT_CURRENCY,
      payment_network: PAYMENT_NETWORK,
      breakdown: { monthly_usdt: 0, setup_fee_usdt: 0, first_payment_usdt: 0 },
      message: "Invalid TRC20 wallet address",
    };
  }

  const prices = TIER_PRICES_USDT[resolved];
  const monthly = prices.monthly;
  const setup = prices.setup;
  const firstPayment = monthly + setup;
  const now = new Date();
  const periodEnd = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);

  return {
    subscription: {
      id: `sub_${simpleHash(tenantId + ":" + tierName)}`,
      tenant_id: tenantId,
      tier: resolved,
      status: "active",
      payment_method: "UsdtTrc20",
      billing_wallet: walletAddress,
      add_ons: [],
      started_at: now.toISOString(),
      current_period_end: periodEnd.toISOString(),
      trial_ends_at: null,
      auto_renew: true,
      last_payment_tx_hash: null,
      cancelled_at: null,
      cancellation_reason: null,
    },
    payment_required: firstPayment,
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
    breakdown: { monthly_usdt: monthly, setup_fee_usdt: setup, first_payment_usdt: firstPayment },
    message: `Suscripci\u00f3n ${TIER_DISPLAY_NAMES[resolved]} activada. Pago de ${firstPayment} USDT (TRC20) requerido.`,
  };
}

/** Simple hash for IDs (mirrors Rust sha256_short — truncated for ID generation) */
function simpleHash(input: string): string {
  let hash = 0;
  for (let i = 0; i < input.length; i++) {
    const char = input.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  return Math.abs(hash).toString(16).padStart(12, "0").slice(0, 12);
}

function tsGetPaymentVerificationMethods(): PaymentVerificationMethodInfo[] {
  return [
    {
      id: "manual_admin",
      display_name: "Verificaci\u00f3n Manual por Admin",
      description: "Un administrador verifica manualmente el pago USDT TRC20",
      currency: PAYMENT_CURRENCY,
      network: PAYMENT_NETWORK,
    },
    {
      id: "semi_manual_onchain",
      display_name: "Verificaci\u00f3n Semi-Manual On-Chain",
      description: "El sistema verifica on-chain, un admin aprueba",
      currency: PAYMENT_CURRENCY,
      network: PAYMENT_NETWORK,
    },
  ];
}

function tsIsTrialMandatory(): { mandatory_for_all: boolean; trial_is_prerequisite: boolean; duration_days: number; granted_tier: string; message: string; payment_currency: string; payment_network: string } {
  return {
    mandatory_for_all: true,
    trial_is_prerequisite: true,
    duration_days: TRIAL_CONFIG.duration_days,
    granted_tier: TRIAL_CONFIG.granted_tier,
    message: "Todos los usuarios deben iniciar con el trial de 14 d\u00edas del Plan Business. No se puede saltar al pago directamente.",
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
  };
}

function tsCreateManualPaymentRequest(subscriptionId: string, amountUsdt: number, walletFrom: string, platformWallet: string): ManualPaymentRequest {
  const now = new Date();
  return {
    payment_request: {
      payment_id: `pay_${simpleHash(subscriptionId + ":" + amountUsdt + ":" + walletFrom)}`,
      subscription_id: subscriptionId,
      amount_usdt: amountUsdt,
      wallet_from: walletFrom,
      wallet_to: platformWallet,
      tx_hash: null,
      verification_method: "manual_admin",
      status: "awaiting_payment",
      admin_notes: null,
      confirmed_by: null,
      confirmed_at: null,
      created_at: now.toISOString(),
    },
    instructions: {
      step1: `Env\u00eda exactamente ${amountUsdt} USDT por la red TRC20 a la wallet del platform`,
      step2: "Copia el hash de la transacci\u00f3n TRC20",
      step3: "Proporciona el tx_hash para verificaci\u00f3n manual por admin",
      step4: "Un administrador confirmar\u00e1 tu pago manualmente",
    },
    platform_wallet: platformWallet,
    amount_usdt: amountUsdt,
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
    estimated_confirmation_time: "1-24 horas (verificaci\u00f3n manual por admin)",
  };
}

function tsConfirmManualPayment(paymentId: string, txHash: string, confirmedBy: string): { payment_id: string; tx_hash: string; status: string; confirmed_by: string; message: string; payment_currency: string; payment_network: string } | { error: string; details: string } {
  const txValid = txHash.length === 64 && /^[a-fA-F0-9]{64}$/.test(txHash);
  if (!txValid) {
    return {
      error: "Invalid TRC20 transaction hash",
      details: "TRC20 tx hash must be 64 hex characters",
    };
  }
  return {
    payment_id: paymentId,
    tx_hash: txHash,
    status: "awaiting_confirmation",
    confirmed_by: confirmedBy,
    message: "Pago registrado. Un administrador debe confirmar manualmente la recepci\u00f3n del USDT TRC20.",
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
  };
}

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
