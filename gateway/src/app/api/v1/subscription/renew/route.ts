// ─── Zenic-Agents v3 — Subscription API: Renew ───────────────────────
// POST /api/v1/subscription/renew — Renew a subscription

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { canTransitionTo, SubscriptionStatus } from '@/lib/subscription/types';

const RENEWABLE_STATUSES: SubscriptionStatus[] = ['active', 'past_due', 'suspended', 'downgraded'];

export async function POST(req: NextRequest) {
  try {
    const body = await req.json() as {
      tenantId?: string;
      billingCycle?: 'monthly' | 'annual';
    };

    if (!body.tenantId) {
      return NextResponse.json(
        { error: 'tenantId is required' },
        { status: 400 },
      );
    }

    const { tenantId } = body;

    const subscription = await db.tenantSubscription.findUnique({
      where: { tenantId },
    });

    if (!subscription) {
      return NextResponse.json(
        { error: 'Subscription not found' },
        { status: 404 },
      );
    }

    const currentStatus = subscription.status as SubscriptionStatus;

    // Check if subscription can be renewed
    if (currentStatus === 'cancelled' || currentStatus === 'expired') {
      return NextResponse.json(
        { error: `Subscription in '${currentStatus}' status cannot be renewed. Please sign up again.` },
        { status: 400 },
      );
    }

    if (currentStatus === 'trial') {
      return NextResponse.json(
        { error: 'Trial subscription cannot be renewed. Please make a payment to convert to active.' },
        { status: 400 },
      );
    }

    if (!RENEWABLE_STATUSES.includes(currentStatus)) {
      return NextResponse.json(
        { error: `Subscription in '${currentStatus}' status cannot be renewed.` },
        { status: 400 },
      );
    }

    // Set up new billing period
    const now = new Date();
    const periodEnd = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);

    const targetStatus: SubscriptionStatus = 'active';

    if (!canTransitionTo(currentStatus, targetStatus)) {
      return NextResponse.json(
        { error: `Cannot transition subscription from '${currentStatus}' to '${targetStatus}'` },
        { status: 400 },
      );
    }

    const updated = await db.tenantSubscription.update({
      where: { tenantId },
      data: {
        status: targetStatus,
        currentPeriodStart: now,
        currentPeriodEnd: periodEnd,
      },
    });

    return NextResponse.json({
      data: updated,
      message: 'Subscription renewed successfully. New billing period started.',
    });
  } catch (error) {
    console.error('[Subscription Renew POST]', error);
    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 },
    );
  }
}
