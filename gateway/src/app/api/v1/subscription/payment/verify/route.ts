// ─── Zenic-Agents v3 — Payment Verify ──────────────────────────────────
// POST /api/v1/subscription/payment/verify
// Verify a USDT TRC20 payment for a subscription.
// Manual admin verification required — status defaults to "awaiting_confirmation".
// INVARIANT 4: lastPaymentTxHash NOT updated until admin confirms.

import { db } from "@/lib/db";
import { PAYMENT_CURRENCY, PAYMENT_NETWORK } from "@/lib/pricing-engine";
import { requireTenantAuth } from "@/lib/subscription/auth-helpers";
import { NextRequest, NextResponse } from "next/server";

interface VerifyBody {
  subscriptionId: string;
  txHash: string;
  amountUsdt: number;
}

// TRC20 transaction hash format: 64 hex characters
const TRC20_TX_HASH_REGEX = /^[a-fA-F0-9]{64}$/;

/**
 * Get the platform wallet from environment variable.
 * INVARIANT 4: Fail-closed if not configured — never use hardcoded wallet.
 */
function getPlatformWallet(): string {
  const wallet = process.env.USDT_TRC20_COMPANY_WALLET;
  if (!wallet) {
    throw new Error('USDT_TRC20_COMPANY_WALLET env var is required');
  }
  if (!wallet.startsWith('T') || wallet.length !== 34) {
    throw new Error('USDT_TRC20_COMPANY_WALLET is not a valid TRC20 address');
  }
  return wallet;
}

export async function POST(req: NextRequest) {
  // Verify tenant identity
  const auth = requireTenantAuth(req);
  if (auth instanceof Response) return auth;

  try {
    const body: VerifyBody = await req.json();
    const { subscriptionId, txHash, amountUsdt } = body;

    // Validate required fields
    if (!subscriptionId || !txHash || amountUsdt === undefined) {
      return NextResponse.json(
        { error: "Missing required fields: subscriptionId, txHash, amountUsdt" },
        { status: 400 }
      );
    }

    // Validate amount is positive
    if (typeof amountUsdt !== "number" || amountUsdt <= 0) {
      return NextResponse.json(
        { error: "amountUsdt must be a positive number" },
        { status: 400 }
      );
    }

    // Validate txHash format (TRC20 transaction hash is 64 hex chars)
    if (!TRC20_TX_HASH_REGEX.test(txHash)) {
      return NextResponse.json(
        {
          error: "Invalid TRC20 transaction hash format",
          details: "TRC20 tx hash must be a 64-character hexadecimal string",
        },
        { status: 400 }
      );
    }

    // Look up subscription by subscriptionId
    const subscription = await db.subscription.findUnique({
      where: { subscriptionId },
    });

    if (!subscription) {
      return NextResponse.json(
        { error: "Subscription not found" },
        { status: 404 }
      );
    }

    // Verify tenant ownership: the authenticated tenant must own this subscription
    if (subscription.tenantId !== auth.tenantId) {
      return NextResponse.json(
        { error: "Access denied" },
        { status: 403 }
      );
    }

    // Check for duplicate payment with same txHash (double-spend prevention)
    const existingPayment = await db.subscriptionPayment.findUnique({
      where: { txHash },
    });

    if (existingPayment) {
      return NextResponse.json(
        {
          error: "Payment with this transaction hash already exists",
          status: existingPayment.status,
        },
        { status: 400 }
      );
    }

    // Get platform wallet — fail-closed if not configured
    let platformWallet: string;
    try {
      platformWallet = getPlatformWallet();
    } catch {
      return NextResponse.json(
        { error: "Payment verification unavailable", message: "Platform wallet not configured" },
        { status: 503 }
      );
    }

    // Create SubscriptionPayment record with manual admin verification
    const paymentId = `pay_${auth.tenantId.slice(0, 8)}_${Date.now().toString(36)}`;
    const now = new Date();
    const expiresAt = new Date(now.getTime() + 72 * 60 * 60 * 1000); // 72h for manual admin review

    // Payment is created as "awaiting_confirmation" — admin must manually confirm
    const payment = await db.subscriptionPayment.create({
      data: {
        paymentId,
        subscriptionDbId: subscription.id,
        amountUsdt,
        walletFrom: subscription.billingWalletAddress,
        walletTo: platformWallet, // BUG #2 FIX: Use configured wallet, not "PLATFORM_WALLET_TBD"
        txHash,
        network: "TRC20",
        status: "awaiting_confirmation",
        verificationMethod: "manual_admin",
        adminConfirmedBy: null,
        adminConfirmedAt: null,
        adminNotes: null,
        confirmations: 0,
        requiredConfirmations: 20,
        expiresAt,
        metadata: JSON.stringify({
          submittedAt: now.toISOString(),
          verificationMethod: "manual_admin",
          note: "Payment requires manual admin confirmation via /api/v1/subscription/payment/confirm",
        }),
      },
    });

    // BUG #3 FIX: DO NOT update lastPaymentTxHash until admin confirms
    // The subscription's lastPaymentTxHash will be updated in the
    // /payment/confirm endpoint when the admin actually confirms the payment.

    // Return payment status — awaiting manual admin confirmation
    return NextResponse.json({
      payment: {
        paymentId: payment.paymentId,
        subscriptionId,
        amountUsdt: payment.amountUsdt,
        walletFrom: payment.walletFrom,
        walletTo: payment.walletTo,
        txHash: payment.txHash,
        network: payment.network,
        status: payment.status,
        verificationMethod: payment.verificationMethod,
        confirmations: payment.confirmations,
        requiredConfirmations: payment.requiredConfirmations,
        expiresAt: payment.expiresAt?.toISOString(),
        createdAt: payment.createdAt.toISOString(),
      },
      verification: {
        txHashValid: true,
        paymentCurrency: PAYMENT_CURRENCY,
        paymentNetwork: PAYMENT_NETWORK,
        verificationMethod: "manual_admin",
        adminConfirmationRequired: true,
        adminConfirmEndpoint: "/api/v1/subscription/payment/confirm",
      },
      message: `Payment of ${amountUsdt} USDT (TRC20) is awaiting manual admin confirmation.`,
    });
  } catch (error) {
    console.error("[Payment Verify] Error:", error);
    return NextResponse.json(
      { error: "Internal server error verifying payment" },
      { status: 500 }
    );
  }
}
