/**
 * Feature Gate Middleware for API Routes
 *
 * Checks subscription tier before allowing access to features.
 * Returns 403 if the feature is not available for the tenant's tier.
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

// ─── Tenant Subscription Cache ───

interface TenantSubscriptionInfo {
  tier: SubscriptionTierName;
  addOns: string[];
  status: string;
  expiresAt?: string;
}

// In-memory cache (in production, this would be from DB/API)
const tenantCache = new Map<string, TenantSubscriptionInfo>();

export function setTenantSubscription(tenantId: string, info: TenantSubscriptionInfo): void {
  tenantCache.set(tenantId, info);
}

export function getTenantSubscription(tenantId: string): TenantSubscriptionInfo | undefined {
  return tenantCache.get(tenantId);
}

export function clearTenantSubscription(tenantId: string): boolean {
  return tenantCache.delete(tenantId);
}

export function clearAllTenantSubscriptions(): void {
  tenantCache.clear();
}

// ─── Feature Gate Check ───

export interface FeatureGateResult {
  allowed: boolean;
  reason?: string;
  requiredTier?: SubscriptionTierName;
  currentTier?: SubscriptionTierName;
  upgradeUrl?: string;
}

export function checkFeatureGate(
  tenantId: string,
  feature: string
): FeatureGateResult {
  const subscription = tenantCache.get(tenantId);

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
    // Find the minimum tier required
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

// ─── Usage Limit Check ───

export function checkUsageLimit(
  tenantId: string,
  usageType: keyof TierLimits,
  currentUsage: number,
  requestedAmount: number = 1
): FeatureGateResult {
  const subscription = tenantCache.get(tenantId);

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

// ─── Memory Tier Check ───

export function checkMemoryMechanism(
  tenantId: string,
  mechanism: string
): FeatureGateResult {
  const subscription = tenantCache.get(tenantId);

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

// ─── Memory Mapping Limit Check ───

export function checkMemoryMappingLimit(
  tenantId: string,
  currentMappings: number,
  requestedMappings: number = 1
): FeatureGateResult {
  const subscription = tenantCache.get(tenantId);

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
    // Extract tenant ID from header or default
    const tenantId = req.headers.get('x-tenant-id') || 'default';

    const result = checkFeatureGate(tenantId, feature);

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

    const subscription = getTenantSubscription(tenantId)!;
    return handler(req, { tenantId, tier: subscription.tier });
  };
}
