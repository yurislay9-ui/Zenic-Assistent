// ─── Zenic-Agents v3 — Subscription API: Check Feature ───────────────
// GET /api/v1/subscription/check-feature — Check if a feature is available for a tenant

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import {
  isFeatureAvailable,
  FEATURE_GATES,
  SubscriptionStatus,
  SubscriptionTierName,
} from '@/lib/subscription/types';

const ACTIVE_STATUSES: SubscriptionStatus[] = ['trial', 'active'];

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const tenantId = searchParams.get('tenantId');
    const feature = searchParams.get('feature');

    if (!tenantId || !feature) {
      return NextResponse.json(
        { error: 'tenantId and feature query parameters are required' },
        { status: 400 },
      );
    }

    const subscription = await db.tenantSubscription.findUnique({
      where: { tenantId },
    });

    if (!subscription) {
      return NextResponse.json({
        data: {
          available: false,
          reason: 'No subscription found for tenant',
        },
      });
    }

    const currentStatus = subscription.status as SubscriptionStatus;

    if (!ACTIVE_STATUSES.includes(currentStatus)) {
      return NextResponse.json({
        data: {
          available: false,
          reason: `Subscription status is '${currentStatus}', not active`,
          currentTier: subscription.tier,
        },
      });
    }

    // Parse addOns from JSON string
    let addOns: string[] = [];
    try {
      addOns = JSON.parse(subscription.addOns || '[]');
    } catch {
      addOns = [];
    }

    const available = isFeatureAvailable(feature, subscription.tier as SubscriptionTierName, addOns);

    // Find the feature gate definition for more context
    const gate = FEATURE_GATES.find(g => g.feature === feature);

    return NextResponse.json({
      data: {
        available,
        feature,
        currentTier: subscription.tier,
        minimumTier: gate?.minimumTier,
        description: gate?.description,
        availableAsAddon: gate?.availableAsAddon,
        addonId: gate?.addonId,
        reason: available
          ? undefined
          : gate
            ? `Feature '${feature}' requires ${gate.minimumTier} tier or higher`
            : `Unknown feature '${feature}'`,
      },
    });
  } catch (error) {
    console.error('[Subscription Check Feature GET]', error);
    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 },
    );
  }
}
