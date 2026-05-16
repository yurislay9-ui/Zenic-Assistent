// ─── Zenic-Agents v3 — Subscription API: Get Subscription ────────────
// GET /api/v1/subscription/[tenantId] — Get subscription info for a tenant

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { ACTIVE_STATUSES, SubscriptionStatus } from '@/lib/subscription/types';

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ tenantId: string }> },
) {
  try {
    const { tenantId } = await params;

    if (!tenantId) {
      return NextResponse.json(
        { error: 'tenantId is required' },
        { status: 400 },
      );
    }

    const subscription = await db.tenantSubscription.findUnique({
      where: { tenantId },
      include: {
        trial: true,
        payments: {
          orderBy: { createdAt: 'desc' },
          take: 10,
        },
        usageRecords: true,
      },
    });

    if (!subscription) {
      return NextResponse.json(
        { error: 'Subscription not found' },
        { status: 404 },
      );
    }

    // Auto-expire trials that have passed their expiry date
    if (
      subscription.status === 'trial' &&
      subscription.trial &&
      subscription.trial.status === 'active' &&
      new Date(subscription.trial.expiresAt) < new Date()
    ) {
      await db.$transaction([
        db.trial.update({
          where: { id: subscription.trial.id },
          data: { status: 'expired' },
        }),
        db.tenantSubscription.update({
          where: { tenantId },
          data: { status: 'expired' as SubscriptionStatus },
        }),
      ]);

      // Re-fetch with updated status
      const updated = await db.tenantSubscription.findUnique({
        where: { tenantId },
        include: {
          trial: true,
          payments: { orderBy: { createdAt: 'desc' }, take: 10 },
          usageRecords: true,
        },
      });

      return NextResponse.json({ data: updated });
    }

    const isActive = ACTIVE_STATUSES.includes(subscription.status as SubscriptionStatus);

    return NextResponse.json({
      data: {
        ...subscription,
        isActive,
      },
    });
  } catch (error) {
    console.error('[Subscription GET]', error);
    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 },
    );
  }
}
