// ─── Zenic-Agents v3 — Subscription API: Upgrade ─────────────────────
// POST /api/v1/subscription/upgrade — Upgrade to a higher tier

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import {
  TIER_RANK,
  TIER_PRICES,
  TIER_LIMITS,
  SubscriptionTierName,
  SubscriptionStatus,
  canUpgrade,
  calculateUpgradeProration,
} from '@/lib/subscription/types';

const USAGE_TYPE_MAPPING: Record<string, string> = {
  workflows: 'maxWorkflows',
  actions_daily: 'maxActionsPerDay',
  team_members: 'maxTeamMembers',
  api_calls_per_minute: 'maxApiCallsPerMinute',
  storage_mb: 'maxStorageMb',
  concurrent_sessions: 'maxConcurrentSessions',
  playbooks: 'maxPlaybooks',
  policy_rules: 'maxPolicyRules',
  approval_chain_depth: 'maxApprovalChainDepth',
};

function getLimitForUsageType(usageType: string, tier: SubscriptionTierName): number {
  const limits = TIER_LIMITS[tier];
  if (!limits) return 0;
  const key = USAGE_TYPE_MAPPING[usageType];
  if (!key) return 0;
  const val = limits[key as keyof typeof limits];
  if (typeof val === 'boolean') return val ? 1 : 0;
  return val === Infinity ? 2147483647 : val;
}

const VALID_TIERS: SubscriptionTierName[] = ['starter', 'business', 'enterprise', 'on_premise_enterprise'];
const ACTIVE_STATUSES: SubscriptionStatus[] = ['trial', 'active'];

export async function POST(req: NextRequest) {
  try {
    const body = await req.json() as {
      tenantId?: string;
      targetTier?: string;
    };

    if (!body.tenantId || !body.targetTier) {
      return NextResponse.json(
        { error: 'tenantId and targetTier are required' },
        { status: 400 },
      );
    }

    if (!VALID_TIERS.includes(body.targetTier as SubscriptionTierName)) {
      return NextResponse.json(
        { error: `Invalid targetTier. Must be one of: ${VALID_TIERS.join(', ')}` },
        { status: 400 },
      );
    }

    const targetTier = body.targetTier as SubscriptionTierName;

    const subscription = await db.tenantSubscription.findUnique({
      where: { tenantId: body.tenantId },
    });

    if (!subscription) {
      return NextResponse.json(
        { error: 'Subscription not found' },
        { status: 404 },
      );
    }

    const currentStatus = subscription.status as SubscriptionStatus;

    if (!ACTIVE_STATUSES.includes(currentStatus)) {
      return NextResponse.json(
        { error: `Subscription must be active or in trial to upgrade. Current status: ${currentStatus}` },
        { status: 400 },
      );
    }

    const currentTier = subscription.tier as SubscriptionTierName;

    if (!canUpgrade(currentTier, targetTier)) {
      return NextResponse.json(
        { error: `Cannot upgrade from '${currentTier}' to '${targetTier}'. Target tier must be higher.` },
        { status: 400 },
      );
    }

    // Calculate proration
    const daysRemaining = Math.max(
      0,
      Math.ceil((new Date(subscription.currentPeriodEnd).getTime() - Date.now()) / (24 * 60 * 60 * 1000)),
    );
    const prorationAmount = calculateUpgradeProration(currentTier, targetTier, daysRemaining);

    // Perform upgrade
    const updated = await db.$transaction(async (tx) => {
      // Update subscription tier
      const sub = await tx.tenantSubscription.update({
        where: { tenantId: body.tenantId },
        data: {
          tier: targetTier,
          setupFeePaid: TIER_PRICES[targetTier].setup === 0 ? true : subscription.setupFeePaid,
        },
      });

      // Update usage limits for all usage types
      const usageTypes = Object.keys(USAGE_TYPE_MAPPING);
      for (const usageType of usageTypes) {
        const limitValue = getLimitForUsageType(usageType, targetTier);
        await tx.usageRecordDb.updateMany({
          where: {
            tenantId: body.tenantId,
            usageType,
          },
          data: { limitValue },
        });
      }

      return sub;
    });

    return NextResponse.json({
      data: {
        subscription: updated,
        upgrade: {
          fromTier: currentTier,
          toTier: targetTier,
          prorationAmount,
          daysRemaining,
          newMonthlyPrice: TIER_PRICES[targetTier].monthly,
        },
      },
      message: `Upgraded from ${currentTier} to ${targetTier}. Proration amount: ${prorationAmount} USDT.`,
    });
  } catch (error) {
    console.error('[Subscription Upgrade POST]', error);
    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 },
    );
  }
}
