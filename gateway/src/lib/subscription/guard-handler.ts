/**
 * Subscription-aware route handler for Next.js App Router.
 *
 * Wraps route handlers with feature gate checks before executing.
 * Returns 403 with upgrade info if the feature is not available
 * for the tenant's current subscription tier.
 *
 * BUG #8 FIX: INVARIANT 4 — Deny-by-default when DB is unavailable.
 * Previously defaulted to tier='starter' + status='active' on DB failure,
 * which is a fail-open vulnerability. Now returns 503 (fail-closed).
 *
 * Usage in route.ts:
 * ```typescript
 * import { withSubscriptionGuard } from '@/lib/subscription/guard-handler';
 *
 * export const GET = withSubscriptionGuard(async (req, ctx) => {
 *   // ctx.tenantId, ctx.tier, ctx.addOns are available
 *   // Feature gate has already been checked
 *   return NextResponse.json({ data: 'protected content' });
 * });
 * ```
 */

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { findRouteGuard } from './route-guards';
import { isFeatureAvailable, FEATURE_GATES, SubscriptionTierName } from './types';

// ─── Types ───

export interface SubscriptionContext {
  /** The tenant ID extracted from the x-tenant-id header. */
  tenantId: string;
  /** The tenant's current subscription tier. */
  tier: SubscriptionTierName;
  /** Active add-on IDs for this tenant. */
  addOns: string[];
  /** The subscription record ID from the database. */
  subscriptionId: string;
  /** The subscription status (trial, active, past_due, etc.). */
  status: string;
}

export type GuardedHandler = (
  req: NextRequest,
  ctx: SubscriptionContext
) => Promise<NextResponse> | NextResponse;

// ─── Subscription Lookup (centralized, fail-closed) ───

interface SubscriptionLookupResult {
  tier: SubscriptionTierName;
  addOns: string[];
  subscriptionId: string;
  status: string;
  dbAvailable: boolean;
}

/**
 * Look up a tenant's subscription from the database.
 * INVARIANT 4: If DB is unavailable, returns dbAvailable=false
 * so the caller can deny access (fail-closed).
 */
async function lookupSubscriptionFromDb(tenantId: string): Promise<SubscriptionLookupResult> {
  let tier: SubscriptionTierName = 'starter';
  let addOns: string[] = [];
  let subscriptionId = '';
  let status = 'unknown'; // No subscription found = unknown, NOT 'active'
  let dbAvailable = true;

  try {
    const subscription = await db.tenantSubscription.findUnique({
      where: { tenantId },
    });

    if (subscription) {
      tier = subscription.tier as SubscriptionTierName;
      try {
        addOns = JSON.parse(subscription.addOns);
      } catch {
        addOns = [];
      }
      subscriptionId = subscription.id;
      status = subscription.status;
    }
    // If no subscription found, tier stays 'starter', status stays 'unknown'
  } catch {
    // INVARIANT 4: DB unavailable — flag as unavailable, do NOT default to 'active'
    dbAvailable = false;
  }

  return { tier, addOns, subscriptionId, status, dbAvailable };
}

// ─── Guard Handler ───

/**
 * Creates a subscription-guarded route handler.
 *
 * The returned handler:
 * 1. Extracts the tenant ID from the `x-tenant-id` header.
 * 2. Looks up the route guard for the current path and method.
 * 3. If no guard is defined, passes through to the handler.
 * 4. If a guard exists, looks up the tenant's subscription from the database.
 * 5. INVARIANT 4: If DB is unavailable, DENIES access (fail-closed).
 * 6. Checks if the subscription is active (trial or active status).
 * 7. Checks if the required feature is available for the tenant's tier + add-ons.
 * 8. If all checks pass, calls the handler with the subscription context.
 * 9. If any check fails, returns 403/503 with detailed information.
 */
export function withSubscriptionGuard(
  handler: GuardedHandler
): (req: NextRequest) => Promise<NextResponse> {
  return async (req: NextRequest): Promise<NextResponse> => {
    const pathname = new URL(req.url).pathname;
    const method = req.method;

    // Extract tenant ID from header
    const tenantId = req.headers.get('x-tenant-id') || 'default';

    // Look up route guard
    const guard = findRouteGuard(pathname, method);

    // If no guard defined, allow access (route not gated)
    if (!guard) {
      return handler(req, {
        tenantId,
        tier: 'starter',
        addOns: [],
        subscriptionId: '',
        status: 'unknown',
      });
    }

    // Look up subscription from database
    const lookup = await lookupSubscriptionFromDb(tenantId);

    // INVARIANT 4: Fail-closed when DB is unavailable
    if (!lookup.dbAvailable) {
      return NextResponse.json(
        {
          error: 'ServiceUnavailable',
          message: 'Unable to verify subscription. Access denied for security.',
        },
        { status: 503 }
      );
    }

    const { tier, addOns, subscriptionId, status } = lookup;

    // Check if subscription is active
    if (!['trial', 'active'].includes(status)) {
      return NextResponse.json(
        {
          error: 'SubscriptionNotActive',
          message: `Subscription status is '${status}'. Please activate your subscription.`,
          status,
          upgradeUrl: '/api/v1/subscription/signup',
        },
        { status: 403 }
      );
    }

    // Check feature gate
    const available = isFeatureAvailable(guard.feature, tier, addOns);

    if (!available) {
      const gate = FEATURE_GATES.find(g => g.feature === guard.feature);
      const requiredTier = gate?.minimumTier ?? 'unknown';

      return NextResponse.json(
        {
          error: 'FeatureNotAvailable',
          message: `This endpoint requires the '${requiredTier}' tier or higher.`,
          feature: guard.feature,
          description: guard.description,
          requiredTier,
          currentTier: tier,
          upgradeUrl: '/api/v1/subscription/upgrade',
        },
        { status: 403 }
      );
    }

    // Feature available — call the handler with subscription context
    return handler(req, { tenantId, tier, addOns, subscriptionId, status });
  };
}

// ─── Standalone Feature Check ───

/**
 * Checks a specific feature gate without wrapping a handler.
 * Useful for conditional logic inside route handlers.
 *
 * INVARIANT 4: If DB is unavailable, returns allowed=false.
 *
 * @param tenantId - The tenant ID to check
 * @param feature  - The feature gate identifier (e.g. 'mcp_gateway')
 * @returns Object with allowed status, tier info, and optional reason
 */
export async function checkFeature(
  tenantId: string,
  feature: string
): Promise<{ allowed: boolean; tier: SubscriptionTierName; addOns: string[]; reason?: string }> {
  const lookup = await lookupSubscriptionFromDb(tenantId);

  // INVARIANT 4: DB unavailable = deny
  if (!lookup.dbAvailable) {
    return {
      allowed: false,
      tier: 'starter',
      addOns: [],
      reason: 'Unable to verify subscription — access denied by default',
    };
  }

  const { tier, addOns } = lookup;
  const allowed = isFeatureAvailable(feature, tier, addOns);

  return {
    allowed,
    tier,
    addOns,
    reason: allowed ? undefined : `Feature '${feature}' not available for tier '${tier}'`,
  };
}

/**
 * Gets the full subscription context for a tenant.
 * Useful for routes that need tier/addon info without a specific feature check.
 *
 * INVARIANT 4: If DB is unavailable, returns status='db_unavailable'.
 *
 * @param tenantId - The tenant ID to look up
 * @returns SubscriptionContext with tier, addOns, status, etc.
 */
export async function getSubscriptionContext(tenantId: string): Promise<SubscriptionContext> {
  const lookup = await lookupSubscriptionFromDb(tenantId);

  if (!lookup.dbAvailable) {
    return {
      tenantId,
      tier: 'starter',
      addOns: [],
      subscriptionId: '',
      status: 'db_unavailable',
    };
  }

  return {
    tenantId,
    tier: lookup.tier,
    addOns: lookup.addOns,
    subscriptionId: lookup.subscriptionId,
    status: lookup.status,
  };
}
