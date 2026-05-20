// ─── Zenic-Agents v3 — TypeScript Fallback: Subscription & Payment ────
// Split from wasm-bridge.ts — subscription, payment, and TRC20 validation functions

import type {
  SubscriptionTierName,
  AddressValidation,
  TrialSubscription,
  PaidSubscription,
  PaymentVerificationMethodInfo,
  ManualPaymentRequest,
} from "../types";
import {
  SubscriptionTierName as TierName,
  TIER_PRICES_USDT,
  TRIAL_CONFIG,
  PAYMENT_CURRENCY,
  PAYMENT_NETWORK,
  TIER_DISPLAY_NAMES,
} from "../types";
import { resolveTierName, simpleHash } from "./_ts-fallback-core";

export function tsValidateTrc20Address(address: string): AddressValidation {
  const valid = address.startsWith("T") && address.length === 34 && address.slice(1).split("").every(c => /[A-Za-z0-9]/.test(c));
  return {
    address,
    valid,
    network: PAYMENT_NETWORK,
    currency: PAYMENT_CURRENCY,
    reason: valid ? "Valid TRC20 address format" : "TRC20 address must start with 'T' and be 34 characters alphanumeric",
  };
}

export function tsCreateTrialSubscription(tenantId: string, email: string): TrialSubscription {
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
    message: `Trial de ${config.duration_days} días activado. Acceso completo al Plan Business.`,
    payment_required: false,
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
  };
}

export function tsConvertTrialToPaid(tenantId: string, tierName: string, walletAddress: string): PaidSubscription {
  const resolved = resolveTierName(tierName);
  if (!resolved || resolved === TierName.TRIAL) {
    return {
      subscription: {
        id: "", tenant_id: tenantId, tier: tierName, status: "active",
        payment_method: "UsdtTrc20", billing_wallet: walletAddress, add_ons: [],
        started_at: new Date().toISOString(), current_period_end: new Date().toISOString(),
        trial_ends_at: null, auto_renew: true, last_payment_tx_hash: null,
        cancelled_at: null, cancellation_reason: null,
      },
      payment_required: 0, payment_currency: PAYMENT_CURRENCY, payment_network: PAYMENT_NETWORK,
      breakdown: { monthly_usdt: 0, setup_fee_usdt: 0, first_payment_usdt: 0 },
      message: "Must convert to a paid tier",
    };
  }

  const walletValid = walletAddress.startsWith("T") && walletAddress.length === 34;
  if (!walletValid) {
    return {
      subscription: {
        id: "", tenant_id: tenantId, tier: resolved, status: "active",
        payment_method: "UsdtTrc20", billing_wallet: walletAddress, add_ons: [],
        started_at: new Date().toISOString(), current_period_end: new Date().toISOString(),
        trial_ends_at: null, auto_renew: true, last_payment_tx_hash: null,
        cancelled_at: null, cancellation_reason: null,
      },
      payment_required: 0, payment_currency: PAYMENT_CURRENCY, payment_network: PAYMENT_NETWORK,
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
    message: `Suscripción ${TIER_DISPLAY_NAMES[resolved]} activada. Pago de ${firstPayment} USDT (TRC20) requerido.`,
  };
}

export function tsGetPaymentVerificationMethods(): PaymentVerificationMethodInfo[] {
  return [
    {
      id: "manual_admin",
      display_name: "Verificación Manual por Admin",
      description: "Un administrador verifica manualmente el pago USDT TRC20",
      currency: PAYMENT_CURRENCY,
      network: PAYMENT_NETWORK,
    },
    {
      id: "semi_manual_onchain",
      display_name: "Verificación Semi-Manual On-Chain",
      description: "El sistema verifica on-chain, un admin aprueba",
      currency: PAYMENT_CURRENCY,
      network: PAYMENT_NETWORK,
    },
  ];
}

export function tsIsTrialMandatory(): { mandatory_for_all: boolean; trial_is_prerequisite: boolean; duration_days: number; granted_tier: string; message: string; payment_currency: string; payment_network: string } {
  return {
    mandatory_for_all: true,
    trial_is_prerequisite: true,
    duration_days: TRIAL_CONFIG.duration_days,
    granted_tier: TRIAL_CONFIG.granted_tier,
    message: "Todos los usuarios deben iniciar con el trial de 14 días del Plan Business. No se puede saltar al pago directamente.",
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
  };
}

export function tsCreateManualPaymentRequest(subscriptionId: string, amountUsdt: number, walletFrom: string, platformWallet: string): ManualPaymentRequest {
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
      step1: `Envía exactamente ${amountUsdt} USDT por la red TRC20 a la wallet del platform`,
      step2: "Copia el hash de la transacción TRC20",
      step3: "Proporciona el tx_hash para verificación manual por admin",
      step4: "Un administrador confirmará tu pago manualmente",
    },
    platform_wallet: platformWallet,
    amount_usdt: amountUsdt,
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
    estimated_confirmation_time: "1-24 horas (verificación manual por admin)",
  };
}

export function tsConfirmManualPayment(paymentId: string, txHash: string, confirmedBy: string): { payment_id: string; tx_hash: string; status: string; confirmed_by: string; message: string; payment_currency: string; payment_network: string } | { error: string; details: string } {
  const txValid = txHash.length === 64 && /^[a-fA-F0-9]{64}$/.test(txHash);
  if (!txValid) {
    return { error: "Invalid TRC20 transaction hash", details: "TRC20 tx hash must be 64 hex characters" };
  }
  return {
    payment_id: paymentId,
    tx_hash: txHash,
    status: "awaiting_confirmation",
    confirmed_by: confirmedBy,
    message: "Pago registrado. Un administrador debe confirmar manualmente la recepción del USDT TRC20.",
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
  };
}
