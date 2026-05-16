// ─── Zenic-Agents v3 — Subscription API: Cancel ──────────────────────
// POST /api/v1/subscription/cancel — Cancel a subscription

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { canTransitionTo, SubscriptionStatus } from '@/lib/subscription/types';

const CANCELLABLE_STATUSES: SubscriptionStatus[] = ['trial', 'active', 'past_due', 'suspended', 'downgraded'];

export async function POST(req: NextRequest) {
  try {
    const body = await req.json() as {
      tenantId?: string;
      reason?: string;
    };

    if (!body.tenantId) {
      return NextResponse.json(
        { error: 'tenantId is required' },
        { status: 400 },
      );
    }

    const { tenantId, reason } = body;

    const subscription = await db.tenantSubscription.findUnique({
      where: { tenantId },
      include: { trial: true },
    });

    if (!subscription) {
      return NextResponse.json(
        { error: 'Subscription not found' },
        { status: 404 },
      );
    }

    const currentStatus = subscription.status as SubscriptionStatus;

    if (!CANCELLABLE_STATUSES.includes(currentStatus)) {
      return NextResponse.json(
        { error: `Subscription in status '${currentStatus}' cannot be cancelled. Cancellable statuses: ${CANCELLABLE_STATUSES.join(', ')}` },
        { status: 400 },
      );
    }

    if (!canTransitionTo(currentStatus, 'cancelled')) {
      return NextResponse.json(
        { error: `Cannot transition subscription from '${currentStatus}' to 'cancelled'` },
        { status: 400 },
      );
    }

    const result = await db.$transaction(async (tx) => {
      // Cancel trial if active
      if (subscription.trial && subscription.trial.status === 'active') {
        await tx.trial.update({
          where: { id: subscription.trial.id },
          data: { status: 'cancelled' },
        });
      }

      // Cancel subscription
      const updated = await tx.tenantSubscription.update({
        where: { tenantId },
        data: {
          status: 'cancelled',
          cancelledAt: new Date(),
        },
      });

      // Expire any pending payments
      await tx.usdtPaymentRecord.updateMany({
        where: {
          subscriptionId: subscription.id,
          status: { in: ['pending', 'tx_submitted', 'verifying'] },
        },
        data: { status: 'expired' },
      });

      return updated;
    });

    return NextResponse.json({
      data: result,
      message: reason ? `Subscription cancelled: ${reason}` : 'Subscription cancelled successfully.',
    });
  } catch (error) {
    console.error('[Subscription Cancel POST]', error);
    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 },
    );
  }
}
