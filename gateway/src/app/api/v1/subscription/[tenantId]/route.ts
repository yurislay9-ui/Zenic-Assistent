// ─── Zenic-Agents v3 — Subscription API: Get Subscription ────────────
// GET /api/v1/subscription/[tenantId] — Get subscription info for a tenant
// BUG #5 FIX: No DB mutation on GET — trial expiry is computed, not persisted.
// Use POST /api/v1/subscription/expire-trial to actually expire trials.

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { ACTIVE_STATUSES, SubscriptionStatus } from '@/lib/subscription/types';
import { requireTenantAuth, verifyTenantOwnership } from '@/lib/subscription/auth-helpers';

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ tenantId: string }> },
) {
  // Verify tenant identity
  const auth = requireTenantAuth(req);
  if (auth instanceof Response) return auth;

  try {
    const { tenantId } = await params;

    if (!tenantId) {
      return NextResponse.json(
        { error: 'tenantId is required' },
        { status: 400 },
      );
    }

    // Verify tenant ownership: caller can only read their own subscription
    if (!verifyTenantOwnership(auth, tenantId)) {
      return NextResponse.json(
        { error: 'Access denied' },
        { status: 403 },
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

    // BUG #5 FIX: Detect expired trial but DO NOT mutate the DB on GET.
    // Return the computed status and a flag so the client can act on it.
    // Actual DB mutation should happen via a dedicated maintenance endpoint.
    let computedStatus = subscription.status as SubscriptionStatus;
    let trialExpired = false;

    if (
      subscription.status === 'trial' &&
      subscription.trial &&
      subscription.trial.status === 'active' &&
      new Date(subscription.trial.expiresAt) < new Date()
    ) {
      computedStatus = 'expired';
      trialExpired = true;
    }

    const isActive = ACTIVE_STATUSES.includes(computedStatus);

    return NextResponse.json({
      data: {
        ...subscription,
        status: computedStatus,
        isActive,
        trialExpired,
        // Client should call POST /api/v1/subscription/expire-trial if trialExpired
        // to actually persist the expiry in the database
        actions: trialExpired
          ? { expireTrial: 'POST /api/v1/subscription/expire-trial' }
          : undefined,
      },
    });
  } catch (error) {
    console.error('[Subscription GET]', error);
    // BUG #9 FIX: Never expose String(error) to client
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 },
    );
  }
}
