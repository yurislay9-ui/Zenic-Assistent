// ─── Zenic-Agents v3 — Payment Confirm (Admin) ────────────────────────
// POST /api/v1/subscription/payment/confirm
// Admin confirms a manual USDT TRC20 payment.
// Body: { paymentId, adminUserId, action: "confirm" | "reject", notes?, rejectionReason? }

import { db } from "@/lib/db";
import { PAYMENT_CURRENCY, PAYMENT_NETWORK } from "@/lib/pricing-engine";

interface ConfirmBody {
  paymentId: string;
  adminUserId: string;
  action: "confirm" | "reject";
  notes?: string;
  rejectionReason?: string;
}

export async function POST(request: Request) {
  try {
    const body: ConfirmBody = await request.json();
    const { paymentId, adminUserId, action, notes, rejectionReason } = body;

    if (!paymentId || !adminUserId || !action) {
      return Response.json(
        { error: "Missing required fields: paymentId, adminUserId, action" },
        { status: 400 }
      );
    }

    if (action !== "confirm" && action !== "reject") {
      return Response.json(
        { error: "Action must be 'confirm' or 'reject'" },
        { status: 400 }
      );
    }

    // Look up payment
    const payment = await db.subscriptionPayment.findUnique({
      where: { paymentId },
    });

    if (!payment) {
      return Response.json(
        { error: "Payment not found", paymentId },
        { status: 404 }
      );
    }

    // Check payment is in correct status for admin action
    if (payment.status !== "confirming" && payment.status !== "awaiting_confirmation" && payment.status !== "pending") {
      return Response.json(
        { error: `Payment cannot be confirmed. Current status: ${payment.status}` },
        { status: 400 }
      );
    }

    const now = new Date();

    if (action === "confirm") {
      // Confirm payment
      const updatedPayment = await db.subscriptionPayment.update({
        where: { paymentId },
        data: {
          status: "confirmed",
          confirmedAt: now,
          paidAt: now,
          verificationMethod: "manual_admin",
          adminConfirmedBy: adminUserId,
          adminConfirmedAt: now,
          adminNotes: notes ?? null,
          confirmations: 20,
          metadata: JSON.stringify({
            ...JSON.parse(payment.metadata || "{}"),
            manuallyConfirmedBy: adminUserId,
            manuallyConfirmedAt: now.toISOString(),
            verificationMethod: "manual_admin",
            adminNotes: notes ?? "",
          }),
        },
      });

      // Look up subscription to get tenantId and subscriptionId
      const subscription = await db.subscription.findUnique({
        where: { id: payment.subscriptionDbId },
      });

      // Create ManualPaymentConfirmation record
      await db.manualPaymentConfirmation.create({
        data: {
          paymentId,
          subscriptionId: subscription?.subscriptionId ?? "",
          tenantId: subscription?.tenantId ?? "",
          amountUsdt: payment.amountUsdt,
          txHash: payment.txHash,
          walletFrom: payment.walletFrom,
          walletTo: payment.walletTo,
          verifiedByAdmin: adminUserId,
          adminNotes: notes,
          status: "confirmed",
        },
      });

      // Update subscription status to "active" if it was "pending_payment"
      if (subscription && subscription.status === "pending_payment") {
        await db.subscription.update({
          where: { id: subscription.id },
          data: {
            status: "active",
            lastPaymentTxHash: payment.txHash,
            lastPaymentAmount: payment.amountUsdt,
            lastPaymentAt: now,
            updatedAt: now,
          },
        });
      }

      return Response.json({
        confirmation: {
          paymentId,
          action: "confirmed",
          confirmedBy: adminUserId,
          confirmedAt: now.toISOString(),
          amountUsdt: payment.amountUsdt,
          txHash: payment.txHash,
          paymentCurrency: PAYMENT_CURRENCY,
          paymentNetwork: PAYMENT_NETWORK,
        },
        message: `Pago de ${payment.amountUsdt} USDT (TRC20) confirmado manualmente por admin ${adminUserId}.`,
      });
    } else {
      // Reject payment
      const updatedPayment = await db.subscriptionPayment.update({
        where: { paymentId },
        data: {
          status: "failed",
          verificationMethod: "manual_admin",
          adminConfirmedBy: adminUserId,
          adminConfirmedAt: now,
          adminNotes: notes ?? null,
          metadata: JSON.stringify({
            ...JSON.parse(payment.metadata || "{}"),
            rejectedBy: adminUserId,
            rejectedAt: now.toISOString(),
            rejectionReason: rejectionReason ?? "Admin rejected payment",
            adminNotes: notes ?? "",
          }),
        },
      });

      // Look up subscription to get tenantId and subscriptionId
      const subscription = await db.subscription.findUnique({
        where: { id: payment.subscriptionDbId },
      });

      // Create ManualPaymentConfirmation record
      await db.manualPaymentConfirmation.create({
        data: {
          paymentId,
          subscriptionId: subscription?.subscriptionId ?? "",
          tenantId: subscription?.tenantId ?? "",
          amountUsdt: payment.amountUsdt,
          txHash: payment.txHash,
          walletFrom: payment.walletFrom,
          walletTo: payment.walletTo,
          verifiedByAdmin: adminUserId,
          adminNotes: notes,
          status: "rejected",
          rejectionReason: rejectionReason ?? "Admin rejected payment",
        },
      });

      return Response.json({
        confirmation: {
          paymentId,
          action: "rejected",
          rejectedBy: adminUserId,
          rejectedAt: now.toISOString(),
          reason: rejectionReason ?? "Admin rejected payment",
          paymentCurrency: PAYMENT_CURRENCY,
          paymentNetwork: PAYMENT_NETWORK,
        },
        message: `Pago de ${payment.amountUsdt} USDT (TRC20) rechazado por admin ${adminUserId}.`,
      });
    }
  } catch (error) {
    console.error("[Payment Confirm] Error:", error);
    return Response.json(
      { error: "Internal server error confirming payment" },
      { status: 500 }
    );
  }
}
