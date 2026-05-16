// ─── Zenic-Agents v3 — Subscription API: Record Usage ────────────────
// POST /api/v1/subscription/usage/record — Record usage for a tenant

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
      increment?: number;
      value?: number;
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
    const increment = body.increment ?? 1;

    // Verify subscription exists and is active
    const subscription = await db.tenantSubscription.findUnique({
      where: { tenantId },
    });

    if (!subscription) {
      return NextResponse.json(
        { error: 'Subscription not found' },
        { status: 404 },
      );
    }

    if (!ACTIVE_STATUSES.includes(subscription.status as SubscriptionStatus)) {
      return NextResponse.json(
        { error: `Subscription is not active. Current status: ${subscription.status}` },
        { status: 400 },
      );
    }

    // Find the usage record
    const usageRecord = await db.usageRecordDb.findUnique({
      where: {
        tenantId_usageType: { tenantId, usageType },
      },
    });

    if (!usageRecord) {
      return NextResponse.json(
        { error: `Usage record not found for type '${usageType}'` },
        { status: 404 },
      );
    }

    // Update usage: either set absolute value or increment
    const newValue = body.value !== undefined ? body.value : usageRecord.currentValue + increment;

    const updated = await db.usageRecordDb.update({
      where: {
        tenantId_usageType: { tenantId, usageType },
      },
      data: {
        currentValue: newValue,
      },
    });

    const isOverLimit = updated.currentValue > updated.limitValue;

    return NextResponse.json({
      data: {
        ...updated,
        isOverLimit,
        limitValue: updated.limitValue === 2147483647 ? null : updated.limitValue,
      },
    });
  } catch (error) {
    console.error('[Subscription Usage Record POST]', error);
    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 },
    );
  }
}
