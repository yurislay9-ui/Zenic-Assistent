// ─── Zenic-Agents v3 — Subscription API: Sign Up ─────────────────────
// POST /api/v1/subscription/signup — Sign up with 14-day Business trial

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import {
  TIER_LIMITS,
  SubscriptionTierName,
  SubscriptionStatus,
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

const USAGE_TYPES = Object.keys(USAGE_TYPE_MAPPING) as string[];

function getLimitForUsageType(usageType: string, tier: SubscriptionTierName): number {
  const limits = TIER_LIMITS[tier];
  if (!limits) return 0;
  const key = USAGE_TYPE_MAPPING[usageType];
  if (!key) return 0;
  const val = limits[key as keyof typeof limits];
  if (typeof val === 'boolean') return val ? 1 : 0;
  return val === Infinity ? 2147483647 : val;
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json() as { tenantId?: string };

    if (!body.tenantId) {
      return NextResponse.json(
        { error: 'tenantId is required' },
        { status: 400 },
      );
    }

    const { tenantId } = body;

    // Check if subscription already exists
    const existing = await db.tenantSubscription.findUnique({ where: { tenantId } });
    if (existing) {
      return NextResponse.json(
        { error: 'Subscription already exists', data: existing },
        { status: 409 },
      );
    }

    const now = new Date();
    const trialEnd = new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000);

    // Create trial
    const trial = await db.trial.create({
      data: {
        tenantId,
        tier: 'business',
        startedAt: now,
        expiresAt: trialEnd,
        status: 'active',
      },
    });

    // Create subscription in trial status with Business tier
    const subscription = await db.tenantSubscription.create({
      data: {
        tenantId,
        tier: 'business',
        status: 'trial',
        trialId: trial.id,
        addOns: '[]',
        currentPeriodStart: now,
        currentPeriodEnd: trialEnd,
        setupFeePaid: false,
      },
    });

    // Initialize usage records for all usage types
    for (const usageType of USAGE_TYPES) {
      const limitValue = getLimitForUsageType(usageType, 'business');
      await db.usageRecordDb.create({
        data: { tenantId, usageType, currentValue: 0, limitValue },
      });
    }

    return NextResponse.json(
      { data: { subscription, trial } },
      { status: 201 },
    );
  } catch (error) {
    console.error('[Subscription Signup POST]', error);
    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 },
    );
  }
}
