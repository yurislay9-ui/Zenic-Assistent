// ─── Zenic-Agents v3 — Subscription API: Check Usage ─────────────────
// POST /api/v1/subscription/usage/check — Check if usage limit allows an action

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { SubscriptionStatus } from '@/lib/subscription/types';

const VALID_USAGE_TYPES = [
  'workflows',
  'actions_daily',
  'team_members',
  'api_calls_per_minute',
  'storage_mb',
  'concurrent_sessions',
  'playbooks',
  'policy_rules',
  'approval_chain_depth',
] as const;

type UsageType = (typeof VALID_USAGE_TYPES)[number];

const ACTIVE_STATUSES: SubscriptionStatus[] = ['trial', 'active'];

export async function POST(req: NextRequest) {
  try {
    const body = await req.json() as {
      tenantId?: string;
      usageType?: string;
      requestedAmount?: number;
    };

    if (!body.tenantId || !body.usageType) {
      return NextResponse.json(
        { error: 'tenantId and usageType are required' },
        { status: 400 },
      );
    }

    if (!VALID_USAGE_TYPES.includes(body.usageType as UsageType)) {
      return NextResponse.json(
        { error: `Invalid usageType. Must be one of: ${VALID_USAGE_TYPES.join(', ')}` },
        { status: 400 },
      );
    }

    const { tenantId, usageType } = body;
    const requestedAmount = body.requestedAmount ?? 1;

    // Verify subscription exists and is active
    const subscription = await db.tenantSubscription.findUnique({
      where: { tenantId },
    });

    if (!subscription) {
      return NextResponse.json({
        data: {
          allowed: false,
          reason: 'No subscription found for tenant',
        },
      });
    }

    if (!ACTIVE_STATUSES.includes(subscription.status as SubscriptionStatus)) {
      return NextResponse.json({
        data: {
          allowed: false,
          reason: `Subscription status is '${subscription.status}', not active`,
          currentTier: subscription.tier,
        },
      });
    }

    // Find the usage record
    const usageRecord = await db.usageRecordDb.findUnique({
      where: {
        tenantId_usageType: { tenantId, usageType },
      },
    });

    if (!usageRecord) {
      return NextResponse.json({
        data: {
          allowed: false,
          reason: `Usage record not found for type '${usageType}'`,
        },
      });
    }

    const currentValue = usageRecord.currentValue;
    const limitValue = usageRecord.limitValue;
    const projectedValue = currentValue + requestedAmount;

    // 2147483647 represents Infinity/unlimited
    const isUnlimited = limitValue === 2147483647;

    if (isUnlimited) {
      return NextResponse.json({
        data: {
          allowed: true,
          usageType,
          currentValue,
          limitValue: null,
          requestedAmount,
          projectedValue,
          remaining: null,
        },
      });
    }

    const allowed = projectedValue <= limitValue;
    const remaining = Math.max(0, limitValue - currentValue);

    return NextResponse.json({
      data: {
        allowed,
        usageType,
        currentValue,
        limitValue,
        requestedAmount,
        projectedValue,
        remaining,
        reason: allowed
          ? undefined
          : `Usage limit exceeded for '${usageType}': ${projectedValue}/${limitValue} (current: ${currentValue}, requested: +${requestedAmount})`,
      },
    });
  } catch (error) {
    console.error('[Subscription Usage Check POST]', error);
    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 },
    );
  }
}
