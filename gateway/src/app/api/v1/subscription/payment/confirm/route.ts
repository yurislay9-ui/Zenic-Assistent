// ─── Zenic-Agents v3 — Subscription API: Confirm Payment ─────────────
// POST /api/v1/subscription/payment/confirm — Confirm a payment (admin action)

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { canTransitionTo, SubscriptionStatus } from '@/lib/subscription/types';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json() as {
      paymentId?: string;
      confirmedBy?: string;
      blockNumber?: number;
      notes?: string;
    };

    if (!body.paymentId || !body.confirmedBy) {
      return NextResponse.json(
        { error: 'paymentId and confirmedBy are required' },
        { status: 400 },
      );
    }

    const { paymentId, confirmedBy, blockNumber, notes } = body;

    // Find payment
    const payment = await db.usdtPaymentRecord.findUnique({
      where: { id: paymentId },
      include: { subscription: true },
    });

    if (!payment) {
      return NextResponse.json(
        { error: 'Payment not found' },
        { status: 404 },
      );
    }

    // Only payments with tx_submitted or verifying status can be confirmed
    if (!['tx_submitted', 'verifying'].includes(payment.status)) {
      return NextResponse.json(
        { error: `Payment cannot be confirmed in current status: ${payment.status}` },
        { status: 400 },
      );
    }

    if (!payment.txHash) {
      return NextResponse.json(
        { error: 'Payment must have a tx hash submitted before confirmation' },
        { status: 400 },
      );
    }

    // Use transaction to update payment and subscription atomically
    const result = await db.$transaction(async (tx) => {
      // Update payment status
      const updatedPayment = await tx.usdtPaymentRecord.update({
        where: { id: paymentId },
        data: {
          status: 'confirmed',
          confirmedAt: new Date(),
          confirmedBy,
          blockNumber: blockNumber ?? payment.blockNumber,
          notes: notes ?? payment.notes,
        },
      });

      // Update subscription based on current status
      const subscription = payment.subscription;
      let newStatus: SubscriptionStatus = subscription.status as SubscriptionStatus;

      if (subscription.status === 'trial') {
        // Convert trial to active
        newStatus = 'active';
        // Also mark trial as converted
        if (subscription.trialId) {
          await tx.trial.update({
            where: { id: subscription.trialId },
            data: {
              status: 'converted',
              convertedAt: new Date(),
            },
          });
        }
      } else if (subscription.status === 'past_due') {
        newStatus = 'active';
      } else if (subscription.status === 'suspended') {
        newStatus = 'active';
      }

      if (newStatus !== subscription.status) {
        if (!canTransitionTo(subscription.status as SubscriptionStatus, newStatus)) {
          throw new Error(`Cannot transition subscription from ${subscription.status} to ${newStatus}`);
        }

        // Set up new billing period
        const now = new Date();
        const periodEnd = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);

        await tx.tenantSubscription.update({
          where: { id: subscription.id },
          data: {
            status: newStatus,
            currentPeriodStart: now,
            currentPeriodEnd: periodEnd,
            setupFeePaid: payment.includesSetupFee ? true : subscription.setupFeePaid,
          },
        });
      }

      return updatedPayment;
    });

    return NextResponse.json({
      data: result,
      message: 'Payment confirmed successfully. Subscription updated.',
    });
  } catch (error) {
    console.error('[Subscription Confirm Payment POST]', error);
    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 },
    );
  }
}
