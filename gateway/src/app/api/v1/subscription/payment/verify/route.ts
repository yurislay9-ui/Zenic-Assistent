// ─── Zenic-Agents v3 — Payment Verify ──────────────────────────────────
// POST /api/v1/subscription/payment/verify
// Verify a USDT TRC20 payment for a subscription.
// Manual admin verification required — status defaults to "awaiting_confirmation".

import { db } from "@/lib/db";
import { PAYMENT_CURRENCY, PAYMENT_NETWORK } from "@/lib/pricing-engine";

interface VerifyBody {
  subscriptionId: string;
  txHash: string;
  amountUsdt: number;
}

// TRC20 transaction hash format: 64 hex characters
const TRC20_TX_HASH_REGEX = /^[a-fA-F0-9]{64}$/;

export async function POST(request: Request) {
  try {
    const body: VerifyBody = await request.json();
    const { subscriptionId, txHash, amountUsdt } = body;

    // Validate required fields
    if (!subscriptionId || !txHash || amountUsdt === undefined) {
      return Response.json(
        { error: "Missing required fields: subscriptionId, txHash, amountUsdt" },
        { status: 400 }
      );
    }

    // Validate amount is positive
    if (typeof amountUsdt !== "number" || amountUsdt <= 0) {
      return Response.json(
        { error: "amountUsdt must be a positive number" },
        { status: 400 }
      );
    }

    // Validate txHash format (TRC20 transaction hash is 64 hex chars)
    if (!TRC20_TX_HASH_REGEX.test(txHash)) {
      return Response.json(
        {
          error: "Invalid TRC20 transaction hash format",
          details: "TRC20 tx hash must be a 64-character hexadecimal string",
          received: txHash.length === 64 ? "valid length, invalid characters" : `invalid length (${txHash.length}), expected 64`,
        },
        { status: 400 }
      );
    }

    // Look up subscription by subscriptionId
    const subscription = await db.subscription.findUnique({
      where: { subscriptionId },
    });

    if (!subscription) {
      return Response.json(
        {
          error: "Subscription not found",
          subscriptionId,
        },
        { status: 404 }
      );
    }

    // Check for duplicate payment with same txHash
    const existingPayment = await db.subscriptionPayment.findUnique({
      where: { txHash },
    });

    if (existingPayment) {
      return Response.json(
        {
          error: "Payment with this transaction hash already exists",
          paymentId: existingPayment.paymentId,
          status: existingPayment.status,
          confirmedAt: existingPayment.confirmedAt?.toISOString() ?? null,
          message: "This TRC20 transaction has already been processed.",
        },
        { status: 400 }
      );
    }

    // Create SubscriptionPayment record with manual admin verification
    const paymentId = `pay_${subscription.tenantId.slice(0, 8)}_${Date.now().toString(36)}`;
    const now = new Date();
    const expiresAt = new Date(now.getTime() + 72 * 60 * 60 * 1000); // 72h for manual admin review

    // Payment is created as "awaiting_confirmation" — admin must manually confirm
    const payment = await db.subscriptionPayment.create({
      data: {
        paymentId,
        subscriptionDbId: subscription.id,
        amountUsdt,
        walletFrom: subscription.billingWalletAddress,
        walletTo: "PLATFORM_WALLET_TBD",
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
          verifiedAt: now.toISOString(),
          verificationMethod: "manual_admin",
          note: "Payment requires manual admin confirmation via /api/v1/subscription/payment/confirm",
        }),
      },
    });

    // Update subscription's last payment info
    await db.subscription.update({
      where: { subscriptionId },
      data: {
        lastPaymentTxHash: txHash,
        lastPaymentAmount: amountUsdt,
        lastPaymentAt: now,
        updatedAt: now,
      },
    });

    // Return payment status — awaiting manual admin confirmation
    return Response.json({
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
        amountReceived: amountUsdt,
        paymentCurrency: PAYMENT_CURRENCY,
        paymentNetwork: PAYMENT_NETWORK,
        verificationMethod: "manual_admin",
        adminConfirmationRequired: true,
        adminConfirmEndpoint: "/api/v1/subscription/payment/confirm",
      },
      message: `Payment of ${amountUsdt} USDT (TRC20) is awaiting manual admin confirmation. An admin will review and confirm your payment via /api/v1/subscription/payment/confirm.`,
    });
  } catch (error) {
    console.error("[Payment Verify] Error:", error);
    return Response.json(
      { error: "Internal server error verifying payment" },
      { status: 500 }
    );
  }
}
