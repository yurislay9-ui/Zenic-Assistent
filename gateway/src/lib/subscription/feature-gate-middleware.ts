/**
 * Feature Gate Middleware for API Routes
 *
 * Checks subscription tier before allowing access to features.
 * Returns 403 if the feature is not available for the tenant's tier.
 *
 * BUG #6 FIX: Removed in-memory cache that was never populated.
 * All checks now read from the database for consistency.
 * INVARIANT 4: Deny-by-default if DB is unavailable.
 */

import { NextRequest, NextResponse } from 'next/server';
import {
  isFeatureAvailable,
  SubscriptionTierName,
  TierLimits,
  TIER_LIMITS,
  MEMORY_TIER_CONFIG,
  MemoryTierConfig,
  FEATURE_GATES,
} from './types';
import { db } from '@/lib/db';

// ─── DB-backed Subscription Lookup ───

interface TenantSubscriptionInfo {
  tier: SubscriptionTierName;
  addOns: string[];
  status: string;
  expiresAt?: string;
}

/**
 * Look up a tenant's subscription from the database.
 * This replaces the in-memory cache that was never populated.
 */
async function lookupSubscription(tenantId: string): Promise<TenantSubscriptionInfo | null> {
  try {
    const subscription = await db.tenantSubscription.findUnique({
      where: { tenantId },
    });

    if (!subscription) return null;

    let addOns: string[] = [];
    try {
      addOns = JSON.parse(subscription.addOns as string);
    } catch {
      addOns = [];
    }

    return {
      tier: subscription.tier as SubscriptionTierName,
      addOns,
      status: subscription.status,
    };
  } catch {
    // DB unavailable — return null (INVARIANT 4: deny by default)
    return null;
  }
}

// ─── Feature Gate Check (async, DB-backed) ───

export interface FeatureGateResult {
  allowed: boolean;
  reason?: string;
  requiredTier?: SubscriptionTierName;
  currentTier?: SubscriptionTierName;
  upgradeUrl?: string;
}

/**
 * Check feature gate using the database as the source of truth.
 * No in-memory cache — every check reads the latest subscription state.
 */
export async function checkFeatureGate(
  tenantId: string,
  feature: string
): Promise<FeatureGateResult> {
  const subscription = await lookupSubscription(tenantId);

  if (!subscription) {
    return {
      allowed: false,
      reason: 'No subscription found for tenant',
      upgradeUrl: '/api/v1/subscription/signup',
    };
  }

  if (!['trial', 'active'].includes(subscription.status)) {
    return {
      allowed: false,
      reason: `Subscription status is '${subscription.status}', not active`,
      currentTier: subscription.tier,
    };
  }

  const allowed = isFeatureAvailable(feature, subscription.tier, subscription.addOns);

  if (!allowed) {
    const gate = FEATURE_GATES.find(g => g.feature === feature);
    return {
      allowed: false,
      reason: `Feature '${feature}' requires ${(gate?.minimumTier ?? 'unknown')} tier`,
      requiredTier: gate?.minimumTier,
      currentTier: subscription.tier,
      upgradeUrl: '/api/v1/subscription/upgrade',
    };
  }

  return { allowed: true };
}

// ─── Usage Limit Check (async, DB-backed) ───

export async function checkUsageLimit(
  tenantId: string,
  usageType: keyof TierLimits,
  currentUsage: number,
  requestedAmount: number = 1
): Promise<FeatureGateResult> {
  const subscription = await lookupSubscription(tenantId);

  if (!subscription) {
    return {
      allowed: false,
      reason: 'No subscription found for tenant',
    };
  }

  const limits = TIER_LIMITS[subscription.tier];
  const limit = limits[usageType] as number;

  if (limit === Infinity || limit === 0) {
    if (limit === 0) {
      return {
        allowed: false,
        reason: `Usage type '${usageType}' not available for tier '${subscription.tier}'`,
        currentTier: subscription.tier,
      };
    }
    return { allowed: true };
  }

  if (currentUsage + requestedAmount > limit) {
    return {
      allowed: false,
      reason: `Usage limit exceeded for '${usageType}': ${currentUsage + requestedAmount}/${limit}`,
      currentTier: subscription.tier,
    };
  }

  return { allowed: true };
}

// ─── Memory Tier Check (async, DB-backed) ───

export async function checkMemoryMechanism(
  tenantId: string,
  mechanism: string
): Promise<FeatureGateResult> {
  const subscription = await lookupSubscription(tenantId);

  if (!subscription) {
    return { allowed: false, reason: 'No subscription found for tenant' };
  }

  const config = MEMORY_TIER_CONFIG[subscription.tier];

  if (!config.mechanismsAllowed.includes(mechanism)) {
    return {
      allowed: false,
      reason: `Memory mechanism '${mechanism}' not available for tier '${subscription.tier}'`,
      currentTier: subscription.tier,
    };
  }

  return { allowed: true };
}

// ─── Memory Mapping Limit Check (async, DB-backed) ───

export async function checkMemoryMappingLimit(
  tenantId: string,
  currentMappings: number,
  requestedMappings: number = 1
): Promise<FeatureGateResult> {
  const subscription = await lookupSubscription(tenantId);

  if (!subscription) {
    return { allowed: false, reason: 'No subscription found for tenant' };
  }

  const config: MemoryTierConfig = MEMORY_TIER_CONFIG[subscription.tier];

  if (config.maxMappingsPerMonth === Infinity) {
    return { allowed: true };
  }

  if (currentMappings + requestedMappings > config.maxMappingsPerMonth) {
    return {
      allowed: false,
      reason: `Memory mapping limit exceeded: ${currentMappings + requestedMappings}/${config.maxMappingsPerMonth} per month`,
      currentTier: subscription.tier,
    };
  }

  return { allowed: true };
}

// ─── API Route Middleware ───

export function withFeatureGate(
  feature: string,
  handler: (req: NextRequest, ctx: { tenantId: string; tier: SubscriptionTierName }) => Promise<NextResponse>
) {
  return async (req: NextRequest): Promise<NextResponse> => {
    const tenantId = req.headers.get('x-tenant-id') || 'default';
    const result = await checkFeatureGate(tenantId, feature);

    if (!result.allowed) {
      return NextResponse.json(
        {
          error: 'FeatureNotAvailable',
          message: result.reason,
          requiredTier: result.requiredTier,
          currentTier: result.currentTier,
          upgradeUrl: result.upgradeUrl,
        },
        { status: 403 }
      );
    }

    // Fetch fresh subscription info for handler context
    const subscription = await lookupSubscription(tenantId);
    const tier = subscription?.tier ?? 'starter';

    return handler(req, { tenantId, tier });
  };
}
