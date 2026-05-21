/**
 * CANONICAL feature gate implementation.
 * This is the authoritative source for feature access checks.
 * Uses the WASM pricing engine for evaluation.
 * Do NOT create additional feature-gate modules — extend this one.
 * See: H-97 architectural finding — feature gate consolidation.
 */

// ─── Zenic-Agents v3 — Feature Gate Middleware ──────────────────────────
// USDT TRC20 ONLY. Deny-by-default feature access based on subscription tier.
//
// This is a CRITICAL security module that blocks access to features based
// on the tenant's subscription tier. It uses the pricing engine (WASM bridge
// or TS fallback) to check feature availability and enforces deny-by-default.

import type { FeatureName, FeatureCheck, UsageCheck } from "./types";
import { checkFeature, checkUsage } from "./wasm-bridge";
import { db } from "@/lib/db";

// ═══════════════════════════════════════════════════════════════════════════
// Subscription Lookup
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Look up the subscription for a tenant from the database.
 * Returns the tier name (e.g. "starter", "business", "enterprise", "trial")
 * or null if no active subscription found.
 */
export async function getSubscriptionForTenant(
  tenantId: string
): Promise<{ tier: string; status: string; subscriptionId: string } | null> {
  try {
    const subscription = await db.subscription.findUnique({
      where: { tenantId },
      select: {
        id: true,
        subscriptionId: true,
        tier: true,
        status: true,
      },
    });

    if (!subscription) return null;

    return {
      tier: subscription.tier,
      status: subscription.status,
      subscriptionId: subscription.subscriptionId,
    };
  } catch (error) {
    console.error("[FeatureGate] Error looking up subscription:", error);
    return null;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Feature Access Check (sync, pure — uses pricing engine)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Check if a feature is available for a given tier.
 * Uses the pricing engine (WASM or TS fallback) to determine availability.
 * This is a synchronous, pure function — no DB access.
 */
export function checkFeatureAccess(
  tierName: string,
  feature: FeatureName
): FeatureCheck {
  return checkFeature(tierName, feature);
}

// ═══════════════════════════════════════════════════════════════════════════
// Usage Limit Check (sync, pure — uses pricing engine)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Check if usage is within tier limits.
 * Uses the pricing engine (WASM or TS fallback) to determine limits.
 * This is a synchronous, pure function — no DB access.
 */
export function checkUsageLimit(
  tierName: string,
  resource: string,
  currentUsage: number
): UsageCheck {
  return checkUsage(tierName, resource, currentUsage);
}

// ═══════════════════════════════════════════════════════════════════════════
// Enforce Tier Access (async — DB lookup + pricing engine check)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Enforce that a tenant has access to a feature.
 * Looks up the tenant's subscription from DB, then checks the pricing engine.
 * DENY-BY-DEFAULT: if no subscription found, access is denied.
 *
 * @returns { allowed: boolean; denialReason?: string }
 */
export async function enforceTierAccess(
  tenantId: string,
  feature: FeatureName
): Promise<{ allowed: boolean; denialReason?: string }> {
  // Look up subscription from DB
  const subscription = await getSubscriptionForTenant(tenantId);

  // Deny-by-default: no subscription = no access
  if (!subscription) {
    return {
      allowed: false,
      denialReason: `No subscription found for tenant '${tenantId}'. Access denied by default.`,
    };
  }

  // Check if subscription is in an active state
  const activeStatuses = ["trial", "active"];
  if (!activeStatuses.includes(subscription.status)) {
    return {
      allowed: false,
      denialReason: `Subscription status is '${subscription.status}' for tenant '${tenantId}'. Only 'trial' and 'active' subscriptions can access features.`,
    };
  }

  // Use the pricing engine to check feature availability
  const featureCheck = checkFeature(subscription.tier, feature);

  // Log the access attempt to FeatureAccessLog
  try {
    const subscriptionRecord = await db.subscription.findUnique({
      where: { tenantId },
      select: { id: true },
    });

    if (subscriptionRecord) {
      await db.featureAccessLog.create({
        data: {
          subscriptionDbId: subscriptionRecord.id,
          tenantId,
          feature,
          allowed: featureCheck.available,
          denialReason: featureCheck.denial_reason,
        },
      });
    }
  } catch (error) {
    // Don't block the feature check if logging fails
    console.error("[FeatureGate] Error logging feature access:", error);
  }

  if (!featureCheck.available) {
    return {
      allowed: false,
      denialReason: featureCheck.denial_reason ?? `Feature '${feature}' is not available on tier '${subscription.tier}'.`,
    };
  }

  return { allowed: true };
}

// ═══════════════════════════════════════════════════════════════════════════
// API Route Middleware — requireFeature()
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Create a middleware function for API routes that requires a specific feature.
 *
 * Usage in an API route:
 * ```ts
 * import { requireFeature } from "@/lib/pricing-engine";
 *
 * const requireZ3Solver = requireFeature("PolicyZ3Solver");
 *
 * export async function POST(request: Request) {
 *   const tenantId = request.headers.get("x-tenant-id");
 *   if (!tenantId) {
 *     return Response.json({ error: "Missing tenant ID" }, { status: 400 });
 *   }
 *
 *   const accessCheck = await requireZ3Solver(tenantId);
 *   if (!accessCheck.allowed) {
 *     return Response.json({ error: accessCheck.denialReason }, { status: 403 });
 *   }
 *
 *   // Feature is available, proceed with handler logic
 *   // ...
 * }
 * ```
 *
 * @param feature - The feature name that must be available
 * @returns A function that takes a tenantId and returns an access check result
 */
export function requireFeature(
  feature: FeatureName
): (tenantId: string) => Promise<{ allowed: boolean; denialReason?: string }> {
  return async (tenantId: string) => {
    return enforceTierAccess(tenantId, feature);
  };
}
